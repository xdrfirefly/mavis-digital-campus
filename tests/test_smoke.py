import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as campus

LIVE_VERSION = campus.SCHEMA_VERSION
LIVE_BUILD = f"v{LIVE_VERSION}"
LIVE_SHELL_LABEL = f"{LIVE_BUILD} · Community Contribution Ledger"
LIVE_CACHE_KEY = "098"


def test_active_release_surfaces_align_with_schema_version():
    import json
    version = campus.SCHEMA_VERSION
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    current_readme = readme.split("# Historical baseline:", 1)[0]
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    launcher = (ROOT / "run_windows.bat").read_text(encoding="utf-8")
    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8"))
    assert current_readme.startswith(f"# Mavis Digital Campus v{version}")
    assert f"## v{version} focus" in current_readme and f"Target schema: **{version}**" in current_readme
    assert f"Extract v{version}" in current_readme and f"Start v{version} normally" in current_readme
    assert env_example.startswith(f"# Mavis Digital Campus v{version}")
    assert f"title Mavis Digital Campus v{version}" in launcher and f"MAVIS DIGITAL CAMPUS v{version}" in launcher
    assert f"?v={LIVE_CACHE_KEY}" in launcher
    assert f"<title>Mavis Digital Campus v{version}</title>" in index
    assert manifest["build"] == f"v{version}" and manifest["version"] == version
    assert manifest["ai_runtime"]["stabilization_recovery"]["schema_version"] == version
    for relative in ("ai/gemini_provider.py", "ai/openai_provider.py", "grant_provider.py", "weather_provider.py"):
        assert f"/{version}" in (ROOT / relative).read_text(encoding="utf-8")
    assert "# Historical baseline: v0.8.6.9.5" in readme and "## v0.8.7.4.2" in readme


def test_seed_state_and_executive_summary():
    original = campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH = Path(td) / "test.db"
            campus.init_db()
            state = campus.current_state()
            assert {b["id"] for b in state["buildings"]} == {"manor", "library", "barn", "fruit_forest"}
            assert {a["id"] for a in state["agents"]} == {"chief", "programs", "research", "caretaker", "operations", "grants"}
            buildings = {b["id"]: b for b in state["buildings"]}
            assert (buildings["manor"]["x"], buildings["manor"]["y"]) == (18, 73)
            assert (buildings["library"]["x"], buildings["library"]["y"]) == (79, 73)
            assert (buildings["barn"]["x"], buildings["barn"]["y"]) == (79, 22)
            assert (buildings["fruit_forest"]["x"], buildings["fruit_forest"]["y"]) == (35, 50)
            homes = {a["id"]: a["home_building_id"] for a in state["agents"]}
            assert homes == {"chief": "manor", "programs": "barn", "research": "library", "caretaker": "fruit_forest", "operations": "barn", "grants": "manor"}
            assert state["executive"]["pending_approvals"] == 0
            assert state["executive"]["attention"] == []
            assert state["notes"] == []
    finally:
        campus.DB_PATH = original


def test_v074_static_shell():
    index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert LIVE_SHELL_LABEL in index
    assert "needs-me-btn" in index
    assert "drawerExecutive" in js
    assert "data-note-project" in js
    assert "data-task-status" in js

    assert "right-approval-card" in index
    assert "active-agent-list" not in index
    assert "chief-of-staff/master-sheet.png" in js
    assert "coopenheimer-barn/master-sheet.png" in js
    assert "renderDashboardRails" in js
    for concept in [
        "static/assets/agents/chief-of-staff/master-sheet.png",
        "static/assets/agents/chief-of-staff/portrait.jpg",
        "static/assets/buildings/coopenheimer-barn/master-sheet.png",
        "static/assets/buildings/coopenheimer-barn/hero.jpg",
    ]:
        assert (ROOT / concept).exists(), concept

    for asset in [
        "static/assets/buildings/mavis-manor/map-sprite.svg",
        "static/assets/buildings/coopenheimer-barn/map-sprite.svg",
        "static/assets/buildings/library-of-mavis/map-sprite.svg",
        "static/assets/agents/chief-of-staff/map-sprite.svg",
        "static/assets/agents/programs/map-sprite.svg",
        "static/assets/agents/research/map-sprite.svg",
        "static/assets/props/bridge.svg",
    ]:
        assert (ROOT / asset).exists(), asset


def test_v063_canonical_assets():
    from PIL import Image

    barn = ROOT / "static/assets/buildings/coopenheimer-barn/map-sprite.png"
    barn_medium = ROOT / "static/assets/buildings/coopenheimer-barn/medium-sprite.png"
    agent_sprites = {
        "chief": "stella-sprite.png",
        "programs": "percy-sprite.png",
        "research": "rose-sprite.png",
        "caretaker": "stewart-sprite.png",
        "grants": "vernadette-sprite.png",
        "operations": "poe-sprite.png",
    }
    world_assets = (ROOT / "static/js/world-assets.js").read_text(encoding="utf-8")
    world_css = (ROOT / "static/css/world.css").read_text(encoding="utf-8")

    assert barn.exists()
    assert barn_medium.exists()
    assert "coopenheimer-barn/map-sprite.png" in world_assets
    for agent_id, filename in agent_sprites.items():
        sprite = ROOT / "static/assets/agents" / filename
        assert sprite.exists(), sprite
        assert f"{agent_id}: '/static/assets/agents/{filename}'" in world_assets
        with Image.open(sprite) as img:
            assert img.mode == "RGBA"
            assert img.size == (1254, 1254)
            assert img.getchannel("A").getbbox() is not None
    assert ".building-hit.barn{width:310px}" in world_css
    assert "background-size:192px 192px" in world_css
    assert "background-position:-48px -192px" in world_css

    with Image.open(barn) as img:
        assert img.mode == "RGBA"
        assert img.width >= 400
        assert img.height >= 180
        assert img.getchannel("A").getbbox() is not None

def test_v063_location_panel_stays_repaired():
    world_css = (ROOT / "static/css/world.css").read_text(encoding="utf-8")
    assert "top:45%!important" in world_css
    assert "bottom:auto!important" in world_css


def test_v064_staff_integration():
    state_files = [
        ROOT / "static/assets/agents/programs/master-sheet.png",
        ROOT / "static/assets/agents/programs/portrait.jpg",
        ROOT / "static/assets/agents/research/master-sheet.png",
        ROOT / "static/assets/agents/research/portrait.jpg",
        ROOT / "static/assets/agents/caretaker/master-sheet.png",
        ROOT / "static/assets/agents/caretaker/portrait.jpg",
    ]
    for p in state_files:
        assert p.exists(), p

    app = (ROOT / "app.py").read_text(encoding="utf-8")
    world_assets = (ROOT / "static/js/world-assets.js").read_text(encoding="utf-8")
    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    assert '"caretaker", "Stewart", "Land Steward · Grounds, Infrastructure & Living Systems"' in app
    assert "caretaker: '/static/assets/agents/stewart-sprite.png'" in world_assets
    assert 'data-open-agent="caretaker"' in index


def test_v065_building_integration():
    from PIL import Image
    files = [
        ROOT / "static/assets/buildings/mavis-manor/master-sheet.png",
        ROOT / "static/assets/buildings/mavis-manor/hero.jpg",
        ROOT / "static/assets/buildings/mavis-manor/medium-sprite.png",
        ROOT / "static/assets/buildings/mavis-manor/map-sprite.png",
        ROOT / "static/assets/buildings/library-of-mavis/master-sheet.png",
        ROOT / "static/assets/buildings/library-of-mavis/hero.jpg",
        ROOT / "static/assets/buildings/library-of-mavis/medium-sprite.png",
        ROOT / "static/assets/buildings/library-of-mavis/map-sprite.png",
    ]
    for p in files:
        assert p.exists(), p

    wa = (ROOT / "static/js/world-assets.js").read_text(encoding="utf-8")
    app = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    manifest = (ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8")
    assert "mavis-manor/map-sprite.png" in wa
    assert "library-of-mavis/map-sprite.png" in wa
    assert "Mavis Manor — Concept Sheet" in app
    assert "Library of Mavis — Concept Sheet" in app
    assert "storybook-building-pass-v0.6.9" in manifest

    with Image.open(ROOT / "static/assets/buildings/mavis-manor/map-sprite.png") as img:
        assert img.mode == "RGBA"
        assert img.width >= 200 and img.height >= 100
    with Image.open(ROOT / "static/assets/buildings/library-of-mavis/map-sprite.png") as img:
        assert img.mode == "RGBA"
        assert img.width >= 150 and img.height >= 150


def test_v066_environment_world_pass():
    from PIL import Image

    bg = ROOT / "static/assets/environment/storybook-campus-world-pass.png"
    assert bg.exists()

    css = (ROOT / "static/css/world.css").read_text(encoding="utf-8")
    manifest = (ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8")

    assert "storybook-campus-world-pass.png" in css
    assert ".terrain-base," in css
    assert ".stream-layer," in css
    assert "display:none !important;" in css
    assert "environment_world_pass" in manifest

    with Image.open(bg) as img:
        assert img.size == (1400, 900)


def test_v067_environment_alignment():
    bridge = ROOT / "static/assets/environment/storybook-bridge.svg"
    assert bridge.exists()

    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    css = (ROOT / "static/css/world.css").read_text(encoding="utf-8")
    config = (ROOT / "static/js/world-config.js").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "storybook-bridge.svg" in index
    assert "left:486px !important" in css
    assert "left:647px !important" in css
    assert "left:784px !important" in css
    assert "width:570px !important" in css

    assert "barn: { x: 79, y: 22" in config
    assert "manor: { x: 18, y: 73" in config
    assert "library: { x: 79, y: 73" in config
    assert "bridge_pond: {x:37, y:34}" in config
    assert "bridge_manor: {x:48, y:47}" in config
    assert "bridge_library: {x:55, y:70}" in config

    assert '("manor", "Mavis Manor", "Executive Office", "building", 18, 73)' in app
    assert '("library", "Library of Mavis", "Research & Institutional Knowledge", "building", 79, 73)' in app
    assert '("barn", "Coopenheimer Barn", "Programs & Education", "building", 79, 22)' in app


def test_v068_world_integration_polish():
    from PIL import Image

    world_css = (ROOT / "static/css/world.css").read_text(encoding="utf-8")
    manifest = (ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8")

    assert ".path-layer{" in world_css
    assert "display:none !important;" in world_css
    assert "top:332px !important" in world_css
    assert "brightness(1.16)" in world_css
    assert "storybook-building-pass-v0.6.9" in manifest
    assert "storybook-building-pass-v0.6.9" in manifest

    for rel in [
        "static/assets/buildings/mavis-manor/map-sprite.png",
        "static/assets/buildings/library-of-mavis/map-sprite.png",
    ]:
        with Image.open(ROOT / rel) as img:
            assert img.mode == "RGBA"
            alpha = img.getchannel("A")
            assert alpha.getbbox() is not None
            # At least one corner should be transparent now.
            extrema = alpha.getextrema()
            assert extrema[0] == 0
            assert extrema[1] == 255



def test_v0681_focused_map_fixes():
    from PIL import Image

    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    world_css = (ROOT / "static/css/world.css").read_text(encoding="utf-8")
    manifest = (ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8")

    assert LIVE_SHELL_LABEL in index
    assert "bridge bridge-pond" not in index
    assert "path-patch-pond" not in index
    assert ".bridge-pond," in world_css
    assert "display:none !important;" in world_css
    assert "north-pond-bridge-removed-v0.6.10" in manifest

    for rel in [
        "static/assets/buildings/mavis-manor/map-sprite.png",
        "static/assets/buildings/library-of-mavis/map-sprite.png",
    ]:
        with Image.open(ROOT / rel) as img:
            assert img.mode == "RGBA"
            alpha = img.getchannel("A")
            assert alpha.getbbox() is not None
            extrema = alpha.getextrema()
            assert extrema[0] == 0
            assert extrema[1] == 255


def test_v069_building_style_pass():
    from PIL import Image

    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    world_css = (ROOT / "static/css/world.css").read_text(encoding="utf-8")
    manifest = (ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8")

    assert LIVE_SHELL_LABEL in index
    assert "storybook-building-pass-v0.6.9" in manifest
    assert "north-pond-bridge-removed-v0.6.10" in manifest
    assert "width:245px !important" in world_css
    assert "width:188px !important" in world_css
    assert "width:232px !important" in world_css

    for rel in [
        "static/assets/buildings/mavis-manor/map-sprite.png",
        "static/assets/buildings/library-of-mavis/map-sprite.png",
        "static/assets/buildings/coopenheimer-barn/map-sprite.png",
    ]:
        with Image.open(ROOT / rel) as img:
            assert img.mode == "RGBA"
            alpha = img.getchannel("A")
            assert alpha.getbbox() is not None
            assert alpha.getextrema()[0] == 0
            assert alpha.getextrema()[1] == 255


def test_v0610_removed_north_pond_bridge():
    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    css = (ROOT / "static/css/world.css").read_text(encoding="utf-8")
    manifest = (ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert LIVE_SHELL_LABEL in index
    assert "ASK THE CAMPUS" in index
    assert "CREATE A PROJECT" not in index
    assert "Campus Team" in index
    assert "<strong>Stella</strong>" in index
    assert "<strong>Percy</strong>" in index
    assert "<strong>Rose</strong>" in index
    assert "<strong>Vernadette</strong>" in index
    assert "pond-living-icons" in index
    assert "living-weather-card kind-cloud" in index
    assert "living-moon-chip" in index
    assert "bridge bridge-pond" not in index
    assert "path-patch-pond" not in index
    assert ".bridge-pond," in css
    assert "display:none !important;" in css
    assert "north-pond-bridge-removed-v0.6.10" in manifest
    assert "existing campus geography" in manifest
    assert "clean polished mockup" in manifest
    assert "bridge bridge-pond" not in index


def test_v074_ai_provider_files_and_secret_protection():
    import shutil
    import subprocess
    env_example=(ROOT/'.env.example').read_text(encoding='utf-8')
    gitignore=(ROOT/'.gitignore').read_text(encoding='utf-8')
    index=(ROOT/'static/index.html').read_text(encoding='utf-8')
    js=(ROOT/'static/js/app.js').read_text(encoding='utf-8')
    app_text=(ROOT/'app.py').read_text(encoding='utf-8')

    for rel in ['ai/__init__.py','ai/config.py','ai/provider.py','ai/gemini_provider.py','ai/openai_provider.py','ai/service.py','.env.example']:
        assert (ROOT/rel).exists(), rel

    assert 'GEMINI_API_KEY=PASTE_YOUR_GEMINI_KEY_HERE' in env_example
    assert 'OPENAI_API_KEY=PASTE_YOUR_OPENAI_KEY_HERE' in env_example
    assert 'OPENAI_MODEL=gpt-5.6-terra' in env_example
    assert 'PROGRAMS_PROVIDER=openai' in env_example
    ignore_rules = {line.strip() for line in gitignore.splitlines()}
    assert {'.env', '.env.*', '!.env.example'}.issubset(ignore_rules)
    git = shutil.which('git')
    if git:
        assert subprocess.run(
            [git, 'check-ignore', '--quiet', '--', '.env'],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode == 0
        assert subprocess.run(
            [git, 'ls-files', '--error-unmatch', '--', '.env'],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode == 1
    assert 'AI Providers' in index
    assert 'Test Gemini' in index
    assert 'Test OpenAI' in index
    assert '/api/ai/status' in js
    assert '/api/ai/test/${providerId}' in js
    assert '@app.get("/api/ai/status")' in app_text
    assert '@app.post("/api/ai/test/{provider_id}")' in app_text
    assert 'GEMINI_API_KEY' not in index
    assert 'OPENAI_API_KEY' not in index

def test_v074_env_parser_and_safe_status():
    from ai.config import AISettings,read_env_file
    from ai.service import public_ai_status
    with tempfile.TemporaryDirectory() as td:
        env_path=Path(td)/'.env'
        env_path.write_text(
            '# test\n'
            'GEMINI_API_KEY="gemini-secret"\n'
            'GEMINI_MODEL=gemini-3.5-flash-lite\n'
            'OPENAI_API_KEY="openai-secret"\n'
            'OPENAI_MODEL=gpt-5.6-terra\n'
            'CHIEF_PROVIDER=gemini\n'
            'RESEARCH_PROVIDER=gemini\n'
            'PROGRAMS_PROVIDER=openai\n'
            'CARETAKER_PROVIDER=gemini\n',
            encoding='utf-8'
        )
        values=read_env_file(env_path)
        settings=AISettings.from_mapping(values)
        status=public_ai_status(settings)

        assert settings.provider_configured('gemini')
        assert settings.provider_configured('openai')
        assert settings.role_provider('programs') == 'openai'
        assert status['providers']['gemini']['model']=='gemini-3.5-flash-lite'
        assert status['providers']['openai']['model']=='gpt-5.6-terra'
        assert status['roles']['chief']=='gemini'
        assert status['roles']['programs']=='openai'
        assert 'gemini-secret' not in repr(status)
        assert 'openai-secret' not in repr(status)
        assert status['keys_exposed'] is False

def test_v070_gemini_request_shape_without_network():
    import json
    import ai.gemini_provider as gp
    captured={}
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def read(self): return json.dumps({'candidates':[{'content':{'parts':[{'text':'Mavis Digital Campus AI connection successful.'}]}}]}).encode('utf-8')
    original=gp.urllib.request.urlopen
    try:
        def fake_urlopen(request,timeout): captured['url']=request.full_url; captured['headers']=dict(request.header_items()); captured['payload']=json.loads(request.data.decode('utf-8')); return FakeResponse()
        gp.urllib.request.urlopen=fake_urlopen; provider=gp.GeminiProvider('not-a-real-key','gemini-3.5-flash-lite'); result=provider.generate_text('Reply with exactly: Mavis Digital Campus AI connection successful.',max_output_tokens=40)
    finally: gp.urllib.request.urlopen=original
    assert captured['url'].endswith('/v1beta/models/gemini-3.5-flash-lite:generateContent'); headers={k.lower():v for k,v in captured['headers'].items()}; assert headers['x-goog-api-key']=='not-a-real-key'; assert captured['payload']['contents'][0]['role']=='user'; assert captured['payload']['generationConfig']['maxOutputTokens']==40; assert result.text=='Mavis Digital Campus AI connection successful.'

def test_v070_ai_log_table_exists():
    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/'test.db'; campus.init_db();
            with campus.db() as conn: tables={row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            assert 'ai_calls' in tables; assert campus.current_state()['ai_activity']==[]
    finally: campus.DB_PATH=original


def test_v071_chief_agent_files_and_ui():
    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    prompt = (ROOT / "prompts/chief_of_staff.txt").read_text(encoding="utf-8")

    assert (ROOT / "agents/chief_of_staff.py").exists()
    assert (ROOT / "prompts/chief_of_staff.txt").exists()
    assert "ASK THE CAMPUS" in index
    assert LIVE_SHELL_LABEL in index
    assert "/api/chief/plan" in js
    assert '@app.post("/api/chief/plan")' in app_text
    assert "PLANNING ONLY" in prompt
    assert "Return ONLY valid JSON" in prompt
    assert "chief | research | programs | caretaker" in prompt


def test_v071_chief_plan_normalization():
    from agents.chief_of_staff import normalize_plan

    plan = normalize_plan(
        {
            "project_title": "Document Preservation Class",
            "summary": "Create an all-ages 45-minute preservation class.",
            "success_criteria": ["Usable class plan", "All-ages activity"],
            "tasks": [
                {
                    "title": "Research preservation practices",
                    "owner": "research",
                    "brief": "Prepare a concise evidence-informed preservation brief.",
                },
                {
                    "title": "Develop class outline",
                    "owner": "programs",
                    "brief": "Turn the brief into a 45-minute all-ages lesson.",
                },
            ],
            "questions_for_executive": [],
            "risk_notes": ["Avoid implying legal advice."],
        },
        "Develop a preservation class.",
    )

    assert plan["project_title"] == "Document Preservation Class"
    assert len(plan["tasks"]) == 3
    assert plan["tasks"][0]["owner"] == "research"
    assert plan["tasks"][1]["owner"] == "programs"
    assert plan["tasks"][-1]["owner"] == "chief"
    assert "review" in plan["tasks"][-1]["title"].lower()


def test_v071_chief_plan_parser_with_fake_provider():
    import json
    from ai.provider import GenerationResult
    from agents.chief_of_staff import plan_project

    class FakeProvider:
        def generate_text(self, prompt, max_output_tokens=120):
            assert "EXECUTIVE REQUEST" in prompt
            assert max_output_tokens == 1400
            text = json.dumps({
                "project_title": "Garden Workshop",
                "summary": "Plan a practical workshop.",
                "success_criteria": ["A teachable outline"],
                "tasks": [
                    {"title": "Research topic", "owner": "research", "brief": "Create a brief."},
                    {"title": "Build workshop", "owner": "programs", "brief": "Create a lesson."},
                    {"title": "Review plan", "owner": "chief", "brief": "Review and prepare approval."},
                ],
                "questions_for_executive": [],
                "risk_notes": [],
            })
            return GenerationResult(
                provider="gemini",
                model="fake-gemini",
                text=text,
                input_chars=len(prompt),
                output_chars=len(text),
            )

    result = plan_project(FakeProvider(), "Create a garden workshop.")
    assert result.plan["project_title"] == "Garden Workshop"
    assert len(result.plan["tasks"]) == 3
    assert result.generation.model == "fake-gemini"


def test_v071_database_has_chief_plan_and_task_brief():
    original = campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH = Path(td) / "test.db"
            campus.init_db()
            with campus.db() as conn:
                tables = {row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()}
                task_columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
            assert "chief_plans" in tables
            assert "brief" in task_columns
            state = campus.current_state()
            assert "chief_plans" in state
            assert state["chief_plans"] == []
    finally:
        campus.DB_PATH = original


def test_v071_ai_status_persists_verified_connection_shape():
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '"last_verified"' in app_text
    assert '"Multi-provider routing · no automatic fallback"' in (ROOT / "ai/service.py").read_text(encoding="utf-8")
    assert "operation='connection_test' AND status='Success'" in app_text


def test_v072_execution_engine_is_wired_to_plan_approval():
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "async def execute_approved_plan(project_id: int, *, resume: bool = False, revision: bool = False)" in app_text
    assert "simulated_task_result" in app_text
    assert "Awaiting Execution Review" in app_text
    assert "execution_started" in app_text
    assert "workflow_task = asyncio.create_task(" in app_text
    assert "execute_approved_plan(project_id)" in app_text
    assert "Plan approved. The campus is starting the approved workflow now." in js
    assert "Approved plan is executing" in js
    assert "AI Activity + Cost Controls" in readme


def test_v072_simulated_task_result_is_explicit():
    original = campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH = Path(td) / "test.db"
            campus.init_db()
            now = campus.utc_now()
            with campus.db() as conn:
                cur = conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Test", "Active", now, now),
                )
                project_id = int(cur.lastrowid)
                cur = conn.execute(
                    """
                    INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,
                        "Caretaker test task",
                        "caretaker",
                        "Waiting",
                        1,
                        "Prepare a concise grounds brief.",
                        now,
                        now,
                    ),
                )
                task = conn.execute("SELECT * FROM tasks WHERE id=?", (int(cur.lastrowid),)).fetchone()

            result = campus.simulated_task_result(task)
            assert f"v{campus.SCHEMA_VERSION} simulated execution" in result
            assert "Stewart — Land Steward" in result
            assert "No specialist AI call" in result
            assert "external action" in result
    finally:
        campus.DB_PATH = original


def test_v072_execution_engine_completes_tasks_and_requests_review():
    import asyncio
    import json
    from ai.provider import GenerationResult

    original_db = campus.DB_PATH
    original_pause = campus.pause
    original_get_role_provider = campus.get_role_provider

    class FakeChiefProvider:
        def generate_text(self, prompt, max_output_tokens=120):
            text=json.dumps({
                'review_title':'Execution Test Review',
                'executive_summary':'The internal test package completed successfully.',
                'approval_recommendation':'approve_internal',
                'success_criteria_review':[],
                'research_programs_alignment':[],
                'gaps_or_conflicts':[],
                'verification_before_public_use':[],
                'recommended_revisions':[],
                'executive_decisions_needed':[],
                'final_package_summary':'A completed internal test package.',
                'handoff_note':'Ready for human review.'
            })
            return GenerationResult(
                provider='gemini', model='fake-chief-review', text=text,
                input_chars=len(prompt), output_chars=len(text)
            )
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH = Path(td) / "test.db"
            campus.init_db()
            now = campus.utc_now()

            with campus.db() as conn:
                cur = conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Execution Test", "Active", now, now),
                )
                project_id = int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (project_id, "Caretaker test", "caretaker", "Waiting", 1, "Make a test grounds plan.", now, now),
                )
                conn.execute(
                    """
                    INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (project_id, "Chief review", "chief", "Waiting", 2, "Review the test.", now, now),
                )

            async def no_pause(seconds=0):
                return None

            campus.pause = no_pause
            campus.get_role_provider = lambda role: FakeChiefProvider()
            asyncio.run(campus.execute_approved_plan(project_id))

            with campus.db() as conn:
                project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
                tasks = conn.execute(
                    "SELECT * FROM tasks WHERE project_id=? ORDER BY sequence",
                    (project_id,),
                ).fetchall()
                approval = conn.execute(
                    "SELECT * FROM approvals WHERE project_id=? AND status='Pending' ORDER BY id DESC LIMIT 1",
                    (project_id,),
                ).fetchone()

            assert project["status"] == "Awaiting Execution Review"
            assert all(task["status"] == "Completed" for task in tasks)
            assert all(task["result"] for task in tasks)
            assert approval is not None
            assert approval["title"].startswith("Chief final review:")
    finally:
        campus.pause = original_pause
        campus.get_role_provider = original_get_role_provider
        campus.DB_PATH = original_db


def test_v072_manifest_keeps_specialists_simulated():
    manifest = (ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8")
    assert f'"build": "{LIVE_BUILD}"' in manifest
    assert '"chief_execution": "real-planning-and-final-review"' in manifest
    assert '"research_execution": "real-ai-routed"' in manifest
    assert '"approved_plan_execution": true' in manifest
    assert '"external_actions": false' in manifest


def test_v073_research_agent_files_and_prompt_boundaries():
    prompt = (ROOT / "prompts/research.txt").read_text(encoding="utf-8")
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")

    assert (ROOT / "agents/research.py").exists()
    assert (ROOT / "prompts/research.txt").exists()
    assert "do not have autonomous web browsing" in prompt.lower()
    assert "Do not fabricate citations" in prompt
    assert "verification_needed" in prompt
    assert "execute_real_research_task" in app_text
    assert '"research_task"' in app_text
    assert "AI-generated · Rose · Research" in js


def test_v073_research_normalization_and_rendering():
    from agents.research import normalize_artifact, render_artifact

    artifact = normalize_artifact({
        "executive_summary": "Preserve originals and use redundant digital copies.",
        "findings": [
            "Physical records benefit from stable, dry storage.",
            "Digital preservation requires more than one copy."
        ],
        "practical_recommendations": [
            "Teach a simple redundant-copy habit."
        ],
        "uncertainties": [
            "Exact archival requirements depend on material type."
        ],
        "verification_needed": [
            "Verify current storage guidance before putting specific numbers on a public handout."
        ],
        "handoff_note": "Programs should convert these principles into an all-ages activity."
    })

    rendered = render_artifact(artifact)
    assert artifact["findings"]
    assert "AI-generated — Research" in rendered
    assert "VERIFY BEFORE PUBLIC USE" in rendered
    assert "HANDOFF NOTE" in rendered
    assert "did not autonomously browse the web" in rendered


def test_v073_research_agent_with_fake_provider():
    import json
    from ai.provider import GenerationResult
    from agents.research import run_research

    class FakeProvider:
        def generate_text(self, prompt, max_output_tokens=120):
            assert "APPROVED RESEARCH TASK" in prompt
            assert "CHIEF OF STAFF BRIEF" in prompt
            assert max_output_tokens == 1400
            text = json.dumps({
                "executive_summary": "A useful internal summary.",
                "findings": ["Finding one", "Finding two"],
                "practical_recommendations": ["Recommendation one"],
                "uncertainties": ["Uncertainty one"],
                "verification_needed": ["Verify current guidance before publishing."],
                "handoff_note": "Programs can use this to build the class."
            })
            return GenerationResult(
                provider="gemini",
                model="fake-research-model",
                text=text,
                input_chars=len(prompt),
                output_chars=len(text),
            )

    result = run_research(
        FakeProvider(),
        project_title="Preservation Class",
        project_summary="Build a 45-minute all-ages class.",
        task_title="Research preservation principles",
        task_brief="Prepare the factual foundation.",
        prior_results=[],
    )

    assert result.generation.model == "fake-research-model"
    assert result.artifact["findings"][0] == "Finding one"
    assert "AI-generated — Research" in result.rendered_text


def test_v073_database_has_research_artifacts_table():
    original = campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH = Path(td) / "test.db"
            campus.init_db()
            with campus.db() as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            assert "research_artifacts" in tables
            state = campus.current_state()
            assert state["research_artifacts"] == []
    finally:
        campus.DB_PATH = original


def test_v075_execution_uses_real_research_and_real_programs():
    import asyncio
    import json
    from ai.provider import GenerationResult

    original_db = campus.DB_PATH
    original_pause = campus.pause
    original_get_role_provider = campus.get_role_provider

    class FakeProvider:
        def generate_text(self, prompt, max_output_tokens=120):
            if "FINAL CHIEF TASK:" in prompt:
                assert "COMPLETED STRUCTURED RESEARCH ARTIFACTS" in prompt
                assert "COMPLETED STRUCTURED PROGRAMS ARTIFACTS" in prompt
                assert "Use redundant digital copies." in prompt
                assert "Preserve What Matters" in prompt
                text = json.dumps({
                    "review_title": "Document Preservation Class — Executive Review",
                    "executive_summary": "Research and Programs produced a coherent 45-minute all-ages class package.",
                    "approval_recommendation": "approve_internal",
                    "success_criteria_review": [],
                    "research_programs_alignment": [
                        "Programs used Research guidance about redundant digital copies."
                    ],
                    "gaps_or_conflicts": [],
                    "verification_before_public_use": [
                        "Verify current archival storage guidance before publishing the handout."
                    ],
                    "recommended_revisions": [],
                    "executive_decisions_needed": [
                        "Approve the internal class package."
                    ],
                    "final_package_summary": "A 45-minute lesson plan, materials list, activities, and handout concept.",
                    "handoff_note": "Ready for human executive review."
                })
                return GenerationResult(
                    provider="gemini",
                    model="fake-chief-review-model",
                    text=text,
                    input_chars=len(prompt),
                    output_chars=len(text),
                )

            if "APPROVED RESEARCH TASK" in prompt:
                text = json.dumps({
                    "executive_summary": "Research summary for document preservation.",
                    "findings": ["Use redundant digital copies."],
                    "practical_recommendations": ["Teach participants to keep more than one digital copy."],
                    "uncertainties": [],
                    "verification_needed": ["Verify current archival storage guidance before publication."],
                    "handoff_note": "Programs should build a practical all-ages lesson from this."
                })
                return GenerationResult(
                    provider="gemini",
                    model="fake-research-model",
                    text=text,
                    input_chars=len(prompt),
                    output_chars=len(text),
                )

            assert "APPROVED PROGRAMS TASK" in prompt
            assert "STRUCTURED INTERNAL RESEARCH ARTIFACTS" in prompt
            assert "Use redundant digital copies." in prompt
            text = json.dumps({
                "deliverable_title": "Preserve What Matters",
                "program_summary": "A 45-minute all-ages class about physical and digital document preservation.",
                "audience": "All ages with adult help for younger participants",
                "duration_minutes": 45,
                "objectives": [
                    "Identify important documents.",
                    "Create a simple physical and digital preservation plan."
                ],
                "run_of_show": [
                    {
                        "minutes": 5,
                        "segment": "Welcome",
                        "purpose": "Set the goal.",
                        "facilitator_action": "Ask what documents participants would hate to lose."
                    },
                    {
                        "minutes": 15,
                        "segment": "Physical preservation",
                        "purpose": "Teach safe storage habits.",
                        "facilitator_action": "Demonstrate a simple storage checklist."
                    },
                    {
                        "minutes": 15,
                        "segment": "Digital preservation",
                        "purpose": "Teach redundant copies.",
                        "facilitator_action": "Walk through a three-copy planning exercise."
                    },
                    {
                        "minutes": 10,
                        "segment": "Personal plan",
                        "purpose": "Turn learning into action.",
                        "facilitator_action": "Have participants complete a take-home preservation plan."
                    }
                ],
                "materials": ["Sample folders", "Worksheet"],
                "participant_activities": ["Create a personal preservation checklist."],
                "facilitator_notes": ["Keep technical language simple."],
                "handout_or_resource_ideas": ["One-page document preservation checklist."],
                "research_integration": ["Used Research finding about redundant digital copies."],
                "verification_flags": ["Verify current archival storage guidance before public handout."],
                "handoff_note": "Chief should review wording and verification flags."
            })
            return GenerationResult(
                provider="openai",
                model="fake-programs-model",
                text=text,
                input_chars=len(prompt),
                output_chars=len(text),
            )

    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH = Path(td) / "test.db"
            campus.init_db()
            now = campus.utc_now()

            with campus.db() as conn:
                cur = conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Document Preservation Class", "Active", now, now),
                )
                project_id = int(cur.lastrowid)

                conn.execute(
                    """
                    INSERT INTO chief_plans(
                        project_id,summary,success_criteria_json,questions_json,risk_notes_json,
                        provider,model,created_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,
                        "Develop a 45-minute all-ages class.",
                        "[]", "[]", "[]",
                        "gemini", "fake-chief", now,
                    ),
                )

                for sequence, title, owner, brief in [
                    (1, "Research preservation principles", "research", "Prepare the factual foundation."),
                    (2, "Build the 45-minute class", "programs", "Turn Research into a complete all-ages class."),
                    (3, "Chief review", "chief", "Review the internal work."),
                ]:
                    conn.execute(
                        """
                        INSERT INTO tasks(
                            project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?)
                        """,
                        (project_id, title, owner, "Waiting", sequence, brief, now, now),
                    )

            async def no_pause(seconds=0):
                return None

            campus.pause = no_pause
            campus.get_role_provider = lambda role: FakeProvider()
            asyncio.run(campus.execute_approved_plan(project_id))

            with campus.db() as conn:
                tasks = conn.execute(
                    "SELECT * FROM tasks WHERE project_id=? ORDER BY sequence",
                    (project_id,),
                ).fetchall()
                research_artifact = conn.execute(
                    "SELECT * FROM research_artifacts WHERE project_id=?",
                    (project_id,),
                ).fetchone()
                programs_artifact = conn.execute(
                    "SELECT * FROM programs_artifacts WHERE project_id=?",
                    (project_id,),
                ).fetchone()
                chief_review_artifact = conn.execute(
                    "SELECT * FROM chief_review_artifacts WHERE project_id=?",
                    (project_id,),
                ).fetchone()
                approval = conn.execute(
                    "SELECT * FROM approvals WHERE project_id=? AND status='Pending' ORDER BY id DESC LIMIT 1",
                    (project_id,),
                ).fetchone()
                calls = conn.execute(
                    "SELECT operation,status,provider,model FROM ai_calls ORDER BY id"
                ).fetchall()

            assert tasks[0]["status"] == "Completed"
            assert "AI-generated — Research" in tasks[0]["result"]
            assert tasks[1]["status"] == "Completed"
            assert "AI-generated — Programs" in tasks[1]["result"]
            assert "45 minutes" in tasks[1]["result"]

            assert research_artifact is not None
            assert research_artifact["model"] == "fake-research-model"
            assert programs_artifact is not None
            assert programs_artifact["provider"] == "openai"
            assert programs_artifact["model"] == "fake-programs-model"
            assert chief_review_artifact is not None
            assert chief_review_artifact["model"] == "fake-chief-review-model"
            assert "AI-generated — Chief Final Review" in tasks[2]["result"]
            assert approval is not None
            assert approval["title"].startswith("Chief final review:")
            assert "APPROVE INTERNAL" in approval["summary"]

            operations = [(row["operation"], row["status"]) for row in calls]
            assert ("research_task", "Success") in operations
            assert ("programs_task", "Success") in operations
            assert ("chief_final_review", "Success") in operations
    finally:
        campus.pause = original_pause
        campus.get_role_provider = original_get_role_provider
        campus.DB_PATH = original_db



def test_v075_manifest_marks_research_and_programs_real():
    manifest = (ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8")
    assert f'"build": "{LIVE_BUILD}"' in manifest
    assert '"chief_execution": "real-planning-and-final-review"' in manifest
    assert '"research_execution": "real-ai-routed"' in manifest
    assert '"programs_execution": "real-ai-routed"' in manifest
    assert '"caretaker_execution": "simulated"' in manifest
    assert '"autonomous_web_research": false' in manifest



def test_v0731_gemini_timeout_defaults():
    from ai.gemini_provider import GeminiProvider
    provider = GeminiProvider("fake-key", "fake-model")
    assert provider.timeout_seconds == 60.0
    assert provider.max_attempts == 2
    assert provider.retry_delay_seconds == 1.25


def test_v0731_gemini_retries_timeout_then_succeeds():
    import json
    import socket
    import ai.gemini_provider as gp
    attempts = {"count": 0}
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def read(self):
            return json.dumps({"candidates":[{"content":{"parts":[{"text":"Recovered after retry"}]}}]}).encode("utf-8")
    original = gp.urllib.request.urlopen
    try:
        def fake_urlopen(request, timeout):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise socket.timeout("The read operation timed out")
            return FakeResponse()
        gp.urllib.request.urlopen = fake_urlopen
        provider = gp.GeminiProvider("fake-key","fake-model",timeout_seconds=60,max_attempts=2,retry_delay_seconds=0)
        result = provider.generate_text("Test retry",max_output_tokens=20)
    finally:
        gp.urllib.request.urlopen = original
    assert attempts["count"] == 2
    assert result.text == "Recovered after retry"


def test_v0731_gemini_timeout_twice_has_clear_error():
    import socket
    import ai.gemini_provider as gp
    original = gp.urllib.request.urlopen
    try:
        def fake_urlopen(request, timeout):
            raise socket.timeout("The read operation timed out")
        gp.urllib.request.urlopen = fake_urlopen
        provider = gp.GeminiProvider("fake-key","fake-model",timeout_seconds=60,max_attempts=2,retry_delay_seconds=0)
        try:
            provider.generate_text("Test timeout",max_output_tokens=20)
            assert False, "Expected timeout failure"
        except RuntimeError as exc:
            msg=str(exc)
            assert "60 seconds" in msg
            assert "2 attempts" in msg
            assert "temporary" in msg.lower()
    finally:
        gp.urllib.request.urlopen = original


def test_v074_manifest_multi_provider_settings():
    import json
    data=json.loads((ROOT/"static/assets/asset-manifest.json").read_text(encoding="utf-8"))
    assert data["build"] == LIVE_BUILD
    runtime=data["ai_runtime"]
    assert runtime["providers"]["gemini"]["connection_test"] is True
    assert runtime["providers"]["openai"]["default_model"] == "gpt-5.6-terra"
    assert runtime["providers"]["openai"]["api"] == "responses"
    assert runtime["providers"]["openai"]["store"] is False
    assert runtime["default_role_routing"]["programs"] == "openai"
    assert runtime["automatic_provider_fallback"] is False


def test_v074_openai_responses_request_shape_without_network():
    import json
    import ai.openai_provider as op

    captured={}

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self,*args):
            return False
        def read(self):
            return json.dumps({
                "id": "resp_fake",
                "status": "completed",
                "output": [{
                    "type": "message",
                    "content": [{
                        "type": "output_text",
                        "text": "Mavis Digital Campus AI connection successful."
                    }]
                }]
            }).encode("utf-8")

    original=op.urllib.request.urlopen
    try:
        def fake_urlopen(request,timeout):
            captured["url"]=request.full_url
            captured["headers"]=dict(request.header_items())
            captured["payload"]=json.loads(request.data.decode("utf-8"))
            captured["timeout"]=timeout
            return FakeResponse()

        op.urllib.request.urlopen=fake_urlopen
        provider=op.OpenAIProvider("not-a-real-openai-key","gpt-5.6-terra")
        result=provider.generate_text(
            "Reply with exactly: Mavis Digital Campus AI connection successful.",
            max_output_tokens=64,
        )
    finally:
        op.urllib.request.urlopen=original

    assert captured["url"] == "https://api.openai.com/v1/responses"
    headers={k.lower():v for k,v in captured["headers"].items()}
    assert headers["authorization"] == "Bearer not-a-real-openai-key"
    assert captured["payload"]["model"] == "gpt-5.6-terra"
    assert captured["payload"]["max_output_tokens"] == 64
    assert captured["payload"]["store"] is False
    assert captured["payload"]["reasoning"]["effort"] == "none"
    assert captured["timeout"] == 60.0
    assert result.provider == "openai"
    assert result.model == "gpt-5.6-terra"
    assert result.text == "Mavis Digital Campus AI connection successful."


def test_v074_openai_retries_timeout_then_succeeds():
    import json
    import socket
    import ai.openai_provider as op

    attempts={"count":0}

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self,*args):
            return False
        def read(self):
            return json.dumps({
                "status":"completed",
                "output":[{
                    "content":[{
                        "type":"output_text",
                        "text":"Recovered after OpenAI retry"
                    }]
                }]
            }).encode("utf-8")

    original=op.urllib.request.urlopen
    try:
        def fake_urlopen(request,timeout):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise socket.timeout("The read operation timed out")
            return FakeResponse()

        op.urllib.request.urlopen=fake_urlopen
        provider=op.OpenAIProvider(
            "fake-key",
            "gpt-5.6-terra",
            timeout_seconds=60,
            max_attempts=2,
            retry_delay_seconds=0,
        )
        result=provider.generate_text("retry test",max_output_tokens=32)
    finally:
        op.urllib.request.urlopen=original

    assert attempts["count"] == 2
    assert result.text == "Recovered after OpenAI retry"


def test_v074_role_provider_factory():
    from ai.config import AISettings
    from ai.service import get_role_provider

    settings=AISettings.from_mapping({
        "GEMINI_API_KEY":"g-key",
        "GEMINI_MODEL":"gemini-3.5-flash-lite",
        "OPENAI_API_KEY":"o-key",
        "OPENAI_MODEL":"gpt-5.6-terra",
        "CHIEF_PROVIDER":"gemini",
        "RESEARCH_PROVIDER":"gemini",
        "PROGRAMS_PROVIDER":"openai",
        "CARETAKER_PROVIDER":"gemini",
    })

    chief=get_role_provider("chief",settings)
    programs=get_role_provider("programs",settings)

    assert chief.provider_name == "gemini"
    assert chief.model == "gemini-3.5-flash-lite"
    assert programs.provider_name == "openai"
    assert programs.model == "gpt-5.6-terra"


def test_v074_no_automatic_fallback_language_and_routing_ui():
    index=(ROOT/"static/index.html").read_text(encoding="utf-8")
    js=(ROOT/"static/js/app.js").read_text(encoding="utf-8")
    readme=(ROOT/"README.md").read_text(encoding="utf-8")

    assert "Role routing" in index
    assert 'id="route-programs"' in index
    assert "Test OpenAI" in index
    assert "testProviderConnection('openai')" in js
    assert "does not silently transmit the work to another AI vendor" in readme


def test_v075_programs_agent_files_and_prompt_contract():
    prompt=(ROOT/"prompts/programs.txt").read_text(encoding="utf-8")
    app_text=(ROOT/"app.py").read_text(encoding="utf-8")
    js=(ROOT/"static/js/app.js").read_text(encoding="utf-8")

    assert (ROOT/"agents/programs.py").exists()
    assert (ROOT/"prompts/programs.txt").exists()
    assert "Research artifacts as the factual foundation" in prompt
    assert "Do not fabricate citations" in prompt
    assert '"run_of_show"' in prompt
    assert '"research_integration"' in prompt
    assert "execute_real_programs_task" in app_text
    assert '"programs_task"' in app_text
    assert "programs_artifacts" in app_text
    assert "programs_artifacts" in js
    assert "AI-generated · Percy · Programs" in js


def test_v075_programs_normalization_and_rendering():
    from agents.programs import normalize_artifact, render_artifact

    artifact=normalize_artifact({
        "deliverable_title":"Preserve What Matters",
        "program_summary":"An all-ages document preservation class.",
        "audience":"All ages",
        "duration_minutes":45,
        "objectives":["Identify important documents.","Create a preservation plan."],
        "run_of_show":[
            {"minutes":10,"segment":"Opening","purpose":"Orient participants","facilitator_action":"Introduce the problem."},
            {"minutes":35,"segment":"Workshop","purpose":"Practice preservation planning","facilitator_action":"Guide the activity."}
        ],
        "materials":["Worksheet"],
        "participant_activities":["Complete a preservation checklist."],
        "facilitator_notes":["Use plain language."],
        "handout_or_resource_ideas":["Take-home checklist"],
        "research_integration":["Used Research guidance on redundant copies."],
        "verification_flags":["Verify current archival guidance."],
        "handoff_note":"Chief should review the verification flag."
    },"Build a class")

    rendered=render_artifact(artifact)
    assert artifact["duration_minutes"] == 45
    assert sum(item["minutes"] for item in artifact["run_of_show"]) == 45
    assert "AI-generated — Programs" in rendered
    assert "HOW RESEARCH WAS USED" in rendered
    assert "VERIFY BEFORE PUBLIC USE" in rendered
    assert "45 minutes" in rendered


def test_v075_programs_agent_receives_structured_research():
    import json
    from ai.provider import GenerationResult
    from agents.programs import run_programs

    seen={"prompt":""}

    class FakeProvider:
        def generate_text(self,prompt,max_output_tokens=120):
            seen["prompt"]=prompt
            assert max_output_tokens == 3000
            text=json.dumps({
                "deliverable_title":"Test Program",
                "program_summary":"Program summary.",
                "audience":"Community members",
                "duration_minutes":30,
                "objectives":["Learn one useful skill."],
                "run_of_show":[
                    {"minutes":30,"segment":"Workshop","purpose":"Learn","facilitator_action":"Teach and practice."}
                ],
                "materials":[],
                "participant_activities":[],
                "facilitator_notes":[],
                "handout_or_resource_ideas":[],
                "research_integration":["Used the supplied Research finding."],
                "verification_flags":["Keep the Research verification caution."],
                "handoff_note":"Ready for Chief review."
            })
            return GenerationResult(
                provider="openai",
                model="fake-terra",
                text=text,
                input_chars=len(prompt),
                output_chars=len(text),
            )

    result=run_programs(
        FakeProvider(),
        project_title="Test",
        project_summary="Test summary",
        task_title="Build workshop",
        task_brief="Use Research to create the workshop.",
        research_artifacts=[{
            "executive_summary":"Research summary",
            "findings":["Structured research fact"],
            "verification_needed":["Verify this before public use"]
        }],
        prior_results=[],
    )

    assert "STRUCTURED INTERNAL RESEARCH ARTIFACTS" in seen["prompt"]
    assert "Structured research fact" in seen["prompt"]
    assert "Verify this before public use" in seen["prompt"]
    assert result.generation.provider == "openai"
    assert result.generation.model == "fake-terra"
    assert "AI-generated — Programs" in result.rendered_text


def test_v075_database_has_programs_artifacts_table():
    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            with campus.db() as conn:
                tables={
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            assert "programs_artifacts" in tables
            state=campus.current_state()
            assert state["programs_artifacts"] == []
    finally:
        campus.DB_PATH=original


def test_v075_manifest_structured_handoff():
    import json
    data=json.loads((ROOT/"static/assets/asset-manifest.json").read_text(encoding="utf-8"))
    runtime=data["ai_runtime"]
    assert data["build"] == LIVE_BUILD
    assert runtime["research_execution"] == "real-ai-routed"
    assert runtime["programs_execution"] == "real-ai-routed"
    assert runtime["caretaker_execution"] == "simulated"
    assert runtime["structured_handoffs"]["research_to_programs"] is True
    assert runtime["default_role_routing"]["programs"] == "openai"
    assert runtime["providers"]["openai"]["default_model"] == "gpt-5.6-terra"
    assert runtime["automatic_provider_fallback"] is False


def test_v0751_openai_structured_output_request_shape():
    import json
    import ai.openai_provider as op

    captured={}

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self,*args):
            return False
        def read(self):
            return json.dumps({
                "status":"completed",
                "output":[{
                    "type":"message",
                    "content":[{
                        "type":"output_text",
                        "text":json.dumps({
                            "deliverable_title":"Structured Program",
                            "program_summary":"Structured summary",
                            "audience":"All ages",
                            "duration_minutes":45,
                            "objectives":["Learn something"],
                            "run_of_show":[{
                                "minutes":45,
                                "segment":"Workshop",
                                "purpose":"Teach",
                                "facilitator_action":"Facilitate"
                            }],
                            "materials":[],
                            "participant_activities":[],
                            "facilitator_notes":[],
                            "handout_or_resource_ideas":[],
                            "research_integration":[],
                            "verification_flags":[],
                            "handoff_note":"Review"
                        })
                    }]
                }]
            }).encode("utf-8")

    original=op.urllib.request.urlopen
    try:
        def fake_urlopen(request,timeout):
            captured["payload"]=json.loads(request.data.decode("utf-8"))
            captured["timeout"]=timeout
            return FakeResponse()

        op.urllib.request.urlopen=fake_urlopen
        provider=op.OpenAIProvider("fake-key","gpt-5.6-terra")
        schema={
            "type":"object",
            "properties":{"name":{"type":"string"}},
            "required":["name"],
            "additionalProperties":False,
        }
        result=provider.generate_structured(
            "Return structured data.",
            schema_name="test_schema",
            schema=schema,
            max_output_tokens=3600,
        )
    finally:
        op.urllib.request.urlopen=original

    fmt=captured["payload"]["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["name"] == "test_schema"
    assert fmt["strict"] is True
    assert fmt["schema"] == schema
    assert captured["payload"]["text"]["verbosity"] == "low"
    assert captured["payload"]["reasoning"]["effort"] == "none"
    assert captured["payload"]["max_output_tokens"] == 3600
    assert captured["payload"]["store"] is False
    assert result.provider == "openai"


def test_v0751_programs_prefers_structured_provider():
    import json
    from ai.provider import GenerationResult
    from agents.programs import run_programs

    calls={"structured":0,"text":0,"schema":None,"tokens":None}

    class StructuredFakeProvider:
        def generate_structured(self,prompt,*,schema_name,schema,max_output_tokens):
            calls["structured"] += 1
            calls["schema"] = schema
            calls["tokens"] = max_output_tokens
            text=json.dumps({
                "deliverable_title":"Structured Class",
                "program_summary":"A structured class.",
                "audience":"All ages",
                "duration_minutes":45,
                "objectives":["Complete a preservation plan."],
                "run_of_show":[{
                    "minutes":45,
                    "segment":"Workshop",
                    "purpose":"Build the plan",
                    "facilitator_action":"Guide participants."
                }],
                "materials":[],
                "participant_activities":[],
                "facilitator_notes":[],
                "handout_or_resource_ideas":[],
                "research_integration":["Used structured Research."],
                "verification_flags":[],
                "handoff_note":"Ready for Chief review."
            })
            return GenerationResult(
                provider="openai",
                model="gpt-5.6-terra",
                text=text,
                input_chars=len(prompt),
                output_chars=len(text),
            )

        def generate_text(self,*args,**kwargs):
            calls["text"] += 1
            raise AssertionError("Programs should prefer structured output")

    result=run_programs(
        StructuredFakeProvider(),
        project_title="Preservation Class",
        project_summary="Create a class.",
        task_title="Build class",
        task_brief="Build a 45-minute class.",
        research_artifacts=[],
        prior_results=[],
    )

    assert calls["structured"] == 1
    assert calls["text"] == 0
    assert calls["tokens"] == 3600
    assert calls["schema"]["additionalProperties"] is False
    assert "run_of_show" in calls["schema"]["required"]
    assert "AI-generated — Programs" in result.rendered_text


def test_v0751_openai_rejects_incomplete_structured_response():
    import json
    import ai.openai_provider as op

    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self,*args):
            return False
        def read(self):
            return json.dumps({
                "status":"incomplete",
                "incomplete_details":{"reason":"max_output_tokens"},
                "output":[]
            }).encode("utf-8")

    original=op.urllib.request.urlopen
    try:
        op.urllib.request.urlopen=lambda request,timeout: FakeResponse()
        provider=op.OpenAIProvider("fake-key","gpt-5.6-terra")
        try:
            provider.generate_structured(
                "test",
                schema_name="test",
                schema={
                    "type":"object",
                    "properties":{"value":{"type":"string"}},
                    "required":["value"],
                    "additionalProperties":False,
                },
                max_output_tokens=3600,
            )
            assert False, "Expected incomplete response failure"
        except RuntimeError as exc:
            message=str(exc)
            assert "stopped before completing" in message
            assert "max_output_tokens" in message
            assert "partial deliverable" in message
    finally:
        op.urllib.request.urlopen=original


def test_v0751_manifest_marks_programs_structured_output():
    import json
    data=json.loads((ROOT/"static/assets/asset-manifest.json").read_text(encoding="utf-8"))
    assert data["build"] == LIVE_BUILD
    structured=data["ai_runtime"]["programs_structured_output"]
    assert structured["provider"] == "openai"
    assert structured["api"] == "responses"
    assert structured["format"] == "json_schema"
    assert structured["strict"] is True
    assert structured["max_output_tokens"] == 3600


def test_v076_chief_review_files_prompt_and_ui():
    prompt=(ROOT/"prompts/chief_review.txt").read_text(encoding="utf-8")
    app_text=(ROOT/"app.py").read_text(encoding="utf-8")
    js=(ROOT/"static/js/app.js").read_text(encoding="utf-8")

    assert (ROOT/"agents/chief_review.py").exists()
    assert (ROOT/"prompts/chief_review.txt").exists()
    assert "FINAL INTERNAL REVIEW" in prompt
    assert "Compare the completed work against the original success criteria." in prompt
    assert "approve_internal | revise | hold" in prompt
    assert "execute_real_chief_review_task" in app_text
    assert '"chief_final_review"' in app_text
    assert "chief_review_artifacts" in app_text
    assert "chief_review_artifacts" in js
    assert "AI-generated · Stella · Final Review" in js


def test_v076_chief_review_normalization_and_render():
    from agents.chief_review import normalize_artifact, render_artifact

    artifact=normalize_artifact({
        "review_title":"Class Review",
        "executive_summary":"The class package meets the approved internal goal.",
        "approval_recommendation":"approve_internal",
        "success_criteria_review":[{
            "criterion":"Create a 45-minute class",
            "status":"met",
            "evidence":"Programs produced a 45-minute run of show."
        }],
        "research_programs_alignment":["Programs used Research findings."],
        "gaps_or_conflicts":[],
        "verification_before_public_use":["Verify one current archival claim."],
        "recommended_revisions":[],
        "executive_decisions_needed":["Approve the internal package."],
        "final_package_summary":"Lesson plan and handout concept.",
        "handoff_note":"Ready for executive review."
    },project_title="Document Class",success_criteria=["Create a 45-minute class"])

    rendered=render_artifact(artifact)
    assert artifact["approval_recommendation"] == "approve_internal"
    assert artifact["success_criteria_review"][0]["status"] == "met"
    assert "AI-generated — Chief Final Review" in rendered
    assert "APPROVE INTERNAL PACKAGE" in rendered
    assert "VERIFY BEFORE PUBLIC USE" in rendered
    assert "does not authorize email" in rendered.lower()


def test_v076_chief_review_same_provider_json_repair():
    import json
    from ai.provider import GenerationResult
    from agents.chief_review import run_chief_review

    calls={"count":0}

    class FakeGemini:
        def generate_text(self,prompt,max_output_tokens=120):
            calls["count"] += 1
            if calls["count"] == 1:
                text='{"review_title":"Broken review",'
            else:
                assert "repairing your own previous Chief final-review response" in prompt
                text=json.dumps({
                    "review_title":"Repaired Review",
                    "executive_summary":"The package is ready for internal approval.",
                    "approval_recommendation":"approve_internal",
                    "success_criteria_review":[{
                        "criterion":"Produce the class",
                        "status":"met",
                        "evidence":"Programs produced the class."
                    }],
                    "research_programs_alignment":[],
                    "gaps_or_conflicts":[],
                    "verification_before_public_use":[],
                    "recommended_revisions":[],
                    "executive_decisions_needed":[],
                    "final_package_summary":"Completed class package.",
                    "handoff_note":"Review the package."
                })
            return GenerationResult(
                provider="gemini",
                model="fake-gemini",
                text=text,
                input_chars=len(prompt),
                output_chars=len(text),
            )

    result=run_chief_review(
        FakeGemini(),
        project_title="Test Project",
        project_summary="Test",
        task_title="Final review",
        task_brief="Review completed work.",
        success_criteria=["Produce the class"],
        research_artifacts=[],
        programs_artifacts=[],
        other_completed_results=[],
    )

    assert calls["count"] == 2
    assert result.attempt_count == 2
    assert result.artifact["review_title"] == "Repaired Review"
    assert result.generation.input_chars > 0


def test_v076_final_chief_task_executes_after_later_specialist_sequence():
    import asyncio
    import json
    from ai.provider import GenerationResult

    original_db=campus.DB_PATH
    original_pause=campus.pause
    original_get_role_provider=campus.get_role_provider
    seen={"chief_prompt":""}

    class FakeProvider:
        def generate_text(self,prompt,max_output_tokens=120):
            if "APPROVED PROGRAMS TASK" in prompt:
                text=json.dumps({
                    "deliverable_title":"Late Programs Work",
                    "program_summary":"Completed after the Chief task's nominal sequence.",
                    "audience":"Adults",
                    "duration_minutes":30,
                    "objectives":["Complete the program."],
                    "run_of_show":[{
                        "minutes":30,
                        "segment":"Session",
                        "purpose":"Do the work",
                        "facilitator_action":"Facilitate."
                    }],
                    "materials":[],
                    "participant_activities":[],
                    "facilitator_notes":[],
                    "handout_or_resource_ideas":[],
                    "research_integration":[],
                    "verification_flags":[],
                    "handoff_note":"Chief should see this."
                })
                return GenerationResult("openai","fake-programs",text,len(prompt),len(text))

            if "FINAL CHIEF TASK:" in prompt:
                seen["chief_prompt"]=prompt
                assert "Late Programs Work" in prompt
                text=json.dumps({
                    "review_title":"Final Review",
                    "executive_summary":"The later Programs work was included.",
                    "approval_recommendation":"approve_internal",
                    "success_criteria_review":[],
                    "research_programs_alignment":[],
                    "gaps_or_conflicts":[],
                    "verification_before_public_use":[],
                    "recommended_revisions":[],
                    "executive_decisions_needed":[],
                    "final_package_summary":"Programs package reviewed.",
                    "handoff_note":"Ready."
                })
                return GenerationResult("gemini","fake-chief",text,len(prompt),len(text))

            raise AssertionError("Unexpected AI prompt")

    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()
            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Ordering Test","Active",now,now)
                )
                project_id=int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO chief_plans(
                        project_id,summary,success_criteria_json,questions_json,risk_notes_json,
                        provider,model,created_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (project_id,"Ordering test","[]","[]","[]","gemini","fake",now)
                )
                # Chief review has sequence 2, Programs has sequence 3.
                for seq,title,owner,brief in [
                    (1,"Caretaker setup","caretaker","Simulated setup."),
                    (2,"Chief final review","chief","Review all work."),
                    (3,"Late Programs task","programs","Create late program work."),
                ]:
                    conn.execute(
                        """
                        INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?)
                        """,
                        (project_id,title,owner,"Waiting",seq,brief,now,now)
                    )

            async def no_pause(seconds=0):
                return None

            campus.pause=no_pause
            campus.get_role_provider=lambda role: FakeProvider()
            asyncio.run(campus.execute_approved_plan(project_id))

            with campus.db() as conn:
                chief_task=conn.execute(
                    "SELECT * FROM tasks WHERE project_id=? AND owner_agent_id='chief'",
                    (project_id,)
                ).fetchone()
                programs_task=conn.execute(
                    "SELECT * FROM tasks WHERE project_id=? AND owner_agent_id='programs'",
                    (project_id,)
                ).fetchone()

            assert programs_task["status"] == "Completed"
            assert chief_task["status"] == "Completed"
            assert "Late Programs Work" in seen["chief_prompt"]
    finally:
        campus.pause=original_pause
        campus.get_role_provider=original_get_role_provider
        campus.DB_PATH=original_db


def test_v076_database_and_manifest_chief_review():
    import json

    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            with campus.db() as conn:
                tables={
                    row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            assert "chief_review_artifacts" in tables
            assert campus.current_state()["chief_review_artifacts"] == []
    finally:
        campus.DB_PATH=original

    data=json.loads((ROOT/"static/assets/asset-manifest.json").read_text(encoding="utf-8"))
    runtime=data["ai_runtime"]
    assert data["build"] == LIVE_BUILD
    assert runtime["chief_execution"] == "real-planning-and-final-review"
    assert runtime["structured_handoffs"]["research_and_programs_to_chief_review"] is True
    assert runtime["chief_final_review"]["same_provider_json_repair_attempt"] is True
    assert runtime["chief_final_review"]["human_approval_after_review"] is True
    assert runtime["automatic_provider_fallback"] is False


def test_v077_approval_rows_enrich_chief_recommendations():
    import json

    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                recommendations=[
                    ("Approve Project","approve_internal"),
                    ("Revise Project","revise"),
                    ("Hold Project","hold"),
                ]
                for title,recommendation in recommendations:
                    cur=conn.execute(
                        "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                        (title,"Awaiting Execution Review",now,now)
                    )
                    project_id=int(cur.lastrowid)
                    cur=conn.execute(
                        """
                        INSERT INTO tasks(
                            project_id,title,owner_agent_id,status,sequence,brief,result,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            project_id,"Chief final review","chief","Completed",1,
                            "Review it.","AI-generated — Chief Final Review",now,now
                        )
                    )
                    task_id=int(cur.lastrowid)
                    artifact={
                        "review_title":f"{title} Review",
                        "executive_summary":f"Summary for {title}.",
                        "approval_recommendation":recommendation,
                        "success_criteria_review":[],
                        "research_programs_alignment":[],
                        "gaps_or_conflicts":["One gap"] if recommendation=="hold" else [],
                        "verification_before_public_use":["Verify one thing"] if recommendation!="approve_internal" else [],
                        "recommended_revisions":["Revise one thing"] if recommendation=="revise" else [],
                        "executive_decisions_needed":[],
                        "final_package_summary":"Package.",
                        "handoff_note":"Review."
                    }
                    conn.execute(
                        """
                        INSERT INTO chief_review_artifacts(
                            task_id,project_id,content_json,provider,model,attempt_count,created_at
                        ) VALUES(?,?,?,?,?,?,?)
                        """,
                        (
                            task_id,project_id,json.dumps(artifact),
                            "gemini","fake-chief",1,now
                        )
                    )
                    conn.execute(
                        """
                        INSERT INTO approvals(project_id,title,summary,status,created_at,updated_at)
                        VALUES(?,?,?,?,?,?)
                        """,
                        (
                            project_id,f"Chief final review: {title}",
                            f"Summary for {title}.","Pending",now,now
                        )
                    )

                # One ordinary plan approval.
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Plan Project","Awaiting Approval",now,now)
                )
                plan_project_id=int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO approvals(project_id,title,summary,status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        plan_project_id,"Approve plan: Plan Project",
                        "Chief plan waiting.","Pending",now,now
                    )
                )

            state=campus.current_state()
            approvals=state["approvals"]
            executive=state["executive"]

            recs={
                a["chief_recommendation"]
                for a in approvals
                if a["stage"]=="final_review"
            }
            assert recs == {"approve_internal","revise","hold"}
            assert any(a["stage"]=="plan" for a in approvals)
            assert executive["ready_to_approve"] == 1
            assert executive["revision_recommended"] == 1
            assert executive["hold_recommended"] == 1
            assert executive["plan_approvals"] == 1
            assert executive["attention_count"] == 4

            kinds={item["kind"] for item in executive["attention"]}
            assert "approval_ready" in kinds
            assert "revision_recommended" in kinds
            assert "hold_recommended" in kinds
            assert "plan_approval" in kinds
    finally:
        campus.DB_PATH=original


def test_v077_needs_me_and_approval_ready_ui_routing():
    index=(ROOT/"static/index.html").read_text(encoding="utf-8")
    js=(ROOT/"static/js/app.js").read_text(encoding="utf-8")

    assert "Ready to approve" in index
    assert "Stella recommends revision" in index
    assert "Stella recommends hold" in index
    assert 'id="rail-ready-count"' in index
    assert 'id="rail-chief-revisions-count"' in index
    assert 'id="rail-hold-count"' in index
    assert 'id="approval-rail-title"' in index

    assert "function approvalMeta(a)" in js
    assert "Approval Ready" in js
    assert "Revision Recommended" in js
    assert "Stella recommends hold" in js
    assert "Approve internal package" in js
    assert "Request revisions" in js
    assert "Approve anyway" in js
    assert "attention_count" in js


def test_v077_drawer_has_dedicated_scroll_body():
    index=(ROOT/"static/index.html").read_text(encoding="utf-8")
    css=(ROOT/"static/css/world.css").read_text(encoding="utf-8")
    js=(ROOT/"static/js/app.js").read_text(encoding="utf-8")

    assert 'id="drawer-body" class="drawer-body" tabindex="0"' in index
    assert "Scroll for more · Esc closes" in index

    assert ".drawer-body{" in css
    assert "overflow-y:auto" in css
    assert "scrollbar-gutter:stable" in css
    assert "overscroll-behavior:contain" in css
    assert ".hud-drawer{" in css
    assert "bottom:68px" in css
    assert "top:24px" in css

    assert "const priorScroll=sameView?els.drawerBody.scrollTop:0;" in js
    assert "els.drawerBody.scrollTop=sameView?priorScroll:0;" in js
    assert "els.drawerBody.focus({preventScroll:true})" in js
    assert "if(!els.drawer.hidden){openDrawer('map');}" in js


def test_v077_camera_does_not_steal_drawer_wheel():
    camera=(ROOT/"static/js/camera.js").read_text(encoding="utf-8")

    assert "e.target.closest('.hud-drawer,.hud-tasks,.building-panel,input,textarea,select')" in camera
    assert "Never turn those wheel" in camera
    assert "e.preventDefault();" in camera
    assert "button,.building-hit,.hud-drawer,input,textarea,select,label,a" in camera


def test_v077_manifest_decision_and_scroll_runtime():
    import json

    data=json.loads(
        (ROOT/"static/assets/asset-manifest.json").read_text(encoding="utf-8")
    )
    assert data["build"] == LIVE_BUILD

    routing=data["ai_runtime"]["executive_decision_routing"]
    assert routing["enabled"] is True
    assert routing["automatic_decision"] is False
    assert routing["human_authority"] is True
    assert routing["chief_recommendations"] == [
        "approve_internal","revise","hold"
    ]

    scroll=data["ui_runtime"]["drawer_scroll"]
    assert scroll["dedicated_scroll_body"] is True
    assert scroll["preserve_scroll_on_live_refresh"] is True
    assert scroll["map_wheel_interception_fixed"] is True
    assert scroll["escape_closes"] is True


def test_v078_ai_control_schema_and_default():
    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            with campus.db() as conn:
                tables={
                    row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                columns={
                    row[1] for row in conn.execute(
                        "PRAGMA table_info(ai_calls)"
                    ).fetchall()
                }
                control=campus.ai_control_state(conn)

            assert "ai_control" in tables
            assert "project_id" in columns
            assert "task_id" in columns
            assert control["enabled"] is True
            assert control["effective_enabled"] is True
            assert control["daily_estimated_cost_limit_usd"] == 1.0
            assert control["budget_blocked"] is False
    finally:
        campus.DB_PATH=original


def test_v078_openai_list_price_estimation():
    # 4 chars/token => 1000 input tokens and 500 output tokens.
    cost=campus.estimate_openai_list_cost(
        "openai",
        "gpt-5.6-terra",
        4000,
        2000,
    )
    assert cost == 0.008

    assert campus.estimate_openai_list_cost(
        "openai","gpt-5.6-luna",4000,2000
    ) == 0.0008

    assert campus.estimate_openai_list_cost(
        "openai","gpt-5.6-sol",4000,2000
    ) == 0.014

    assert campus.estimate_openai_list_cost(
        "gemini","gemini-3.5-flash-lite",4000,2000
    ) is None


def test_v078_usage_summary_attributes_project_and_task():
    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Cost Test","Active",now,now)
                )
                project_id=int(cur.lastrowid)
                cur=conn.execute(
                    """
                    INSERT INTO tasks(
                        project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Programs cost test","programs","Completed",1,
                        "Test cost attribution.",now,now
                    )
                )
                task_id=int(cur.lastrowid)

                conn.execute(
                    """
                    INSERT INTO ai_calls(
                        provider,model,operation,status,latency_ms,input_chars,output_chars,
                        message,project_id,task_id,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        "openai","gpt-5.6-terra","programs_task","Success",
                        100,4000,2000,"Cost test",project_id,task_id,now
                    )
                )

                usage=campus.ai_usage_summary(conn)

            assert usage["today"]["calls"] == 1
            assert usage["today"]["estimated_input_tokens"] == 1000
            assert usage["today"]["estimated_output_tokens"] == 500
            assert usage["today"]["estimated_openai_list_cost_usd"] == 0.008

            assert len(usage["projects"]) == 1
            group=usage["projects"][0]
            assert group["project_id"] == project_id
            assert group["project_title"] == "Cost Test"
            assert group["calls"] == 1
            assert group["estimated_list_cost_usd"] == 0.008

            call=usage["calls"][0]
            assert call["project_id"] == project_id
            assert call["task_id"] == task_id
            assert call["estimated_list_cost_usd"] == 0.008
            assert call["cost_is_estimate"] is True
    finally:
        campus.DB_PATH=original


def test_v078_emergency_stop_blocks_new_ai_calls():
    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                conn.execute(
                    """
                    UPDATE ai_control
                    SET enabled=0,stopped_reason=?,updated_at=?
                    WHERE id=1
                    """,
                    ("Stopped by test.",now)
                )

            try:
                campus.require_ai_allowed("research_task","gemini")
                assert False, "Expected Emergency Stop AI to block the call"
            except RuntimeError as exc:
                assert "AI is stopped" in str(exc)
                assert "Stopped by test" in str(exc)

            with campus.db() as conn:
                conn.execute(
                    """
                    UPDATE ai_control
                    SET enabled=1,stopped_reason=NULL,updated_at=?
                    WHERE id=1
                    """,
                    (campus.utc_now(),)
                )

            campus.require_ai_allowed("research_task","gemini")
    finally:
        campus.DB_PATH=original


def test_v078_cost_guardrail_blocks_openai_not_gemini():
    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                conn.execute(
                    """
                    UPDATE ai_control
                    SET daily_estimated_cost_limit_usd=?,updated_at=?
                    WHERE id=1
                    """,
                    (0.001,now)
                )
                # Estimated Terra list price = $0.008.
                conn.execute(
                    """
                    INSERT INTO ai_calls(
                        provider,model,operation,status,latency_ms,input_chars,output_chars,
                        message,project_id,task_id,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        "openai","gpt-5.6-terra","programs_task","Success",
                        100,4000,2000,"Guardrail test",None,None,now
                    )
                )

            with campus.db() as conn:
                control=campus.ai_control_state(conn)
            assert control["budget_blocked"] is True
            assert control["effective_enabled"] is True

            try:
                campus.require_ai_allowed("programs_task","openai")
                assert False, "Expected OpenAI guardrail to block the call"
            except RuntimeError as exc:
                assert "guardrail reached" in str(exc)
                assert "$0.0080" in str(exc)

            # The dollar guardrail is specifically OpenAI-list-price based.
            campus.require_ai_allowed("chief_final_review","gemini")
    finally:
        campus.DB_PATH=original


def test_v078_control_endpoints_stop_resume_and_budget():
    import asyncio

    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()

            stopped=asyncio.run(campus.api_ai_stop())
            assert stopped["status"] == "stopped"
            assert stopped["control"]["enabled"] is False

            resumed=asyncio.run(campus.api_ai_resume())
            assert resumed["status"] == "resumed"
            assert resumed["control"]["enabled"] is True

            updated=asyncio.run(
                campus.api_ai_budget(
                    campus.AIBudgetRequest(
                        daily_estimated_cost_limit_usd=0.25
                    )
                )
            )
            assert updated["status"] == "updated"
            assert updated["control"]["daily_estimated_cost_limit_usd"] == 0.25
    finally:
        campus.DB_PATH=original


def test_v078_ai_activity_cost_ui():
    index=(ROOT/"static/index.html").read_text(encoding="utf-8")
    js=(ROOT/"static/js/app.js").read_text(encoding="utf-8")
    css=(ROOT/"static/css/world.css").read_text(encoding="utf-8")
    app_text=(ROOT/"app.py").read_text(encoding="utf-8")

    assert "Emergency Stop AI" in index
    assert "AI Activity & Cost" in index
    assert 'id="ai-budget-input"' in index
    assert 'id="ai-cost-today"' in index
    assert 'id="ai-token-count"' in index

    assert "function drawerAiActivity()" in js
    assert "function renderAiControls()" in js
    assert "function toggleAiStop()" in js
    assert "function saveAiBudget()" in js
    assert "Project AI usage" in js
    assert "Estimated tokens" in js
    assert "not an invoice" in js

    assert ".ai-control-box" in css
    assert ".ai-usage-hero" in css
    assert ".ai-call-card" in css

    assert '@app.post("/api/ai/stop")' in app_text
    assert '@app.post("/api/ai/resume")' in app_text
    assert '@app.post("/api/ai/budget")' in app_text
    assert "require_ai_allowed" in app_text


def test_v078_manifest_activity_and_cost_controls():
    import json

    data=json.loads(
        (ROOT/"static/assets/asset-manifest.json").read_text(encoding="utf-8")
    )
    assert data["build"] == LIVE_BUILD

    controls=data["ai_runtime"]["activity_cost_controls"]
    assert controls["enabled"] is True
    assert controls["project_attribution"] is True
    assert controls["task_attribution"] is True
    assert controls["token_estimate_method"] == "characters_divided_by_4"
    assert controls["openai_prices_per_million"]["gpt-5.6-terra"] == {
        "input":2.0,
        "output":12.0
    }
    assert controls["default_daily_estimated_cost_limit_usd"] == 1.0
    assert controls["zero_disables_guardrail"] is True
    assert controls["guardrail_scope"] == "openai_estimated_list_price"
    assert controls["actual_billing_known"] is False
    assert controls["emergency_stop_new_calls"] is True
    assert controls["inflight_request_may_finish"] is True


def test_v079_schema_health_and_workflow_journal():
    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()

            with campus.db() as conn:
                tables={
                    row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                health=campus.system_health(conn)
                schema=conn.execute(
                    "SELECT schema_version FROM schema_meta WHERE id=1"
                ).fetchone()

            assert "workflow_runs" in tables
            assert "schema_meta" in tables
            assert health["ok"] is True
            assert health["schema_version"] == LIVE_VERSION
            assert health["target_schema_version"] == LIVE_VERSION
            assert schema["schema_version"] == LIVE_VERSION
    finally:
        campus.DB_PATH=original


def test_v079_restart_reconciliation_preserves_completed_work():
    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Restart Test","Active",now,now)
                )
                project_id=int(cur.lastrowid)

                cur=conn.execute(
                    """
                    INSERT INTO tasks(
                        project_id,title,owner_agent_id,status,sequence,brief,result,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Finished task","caretaker","Completed",1,
                        "Finished.","KEEP THIS RESULT",now,now
                    )
                )
                completed_id=int(cur.lastrowid)

                cur=conn.execute(
                    """
                    INSERT INTO tasks(
                        project_id,title,owner_agent_id,status,sequence,brief,result,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Interrupted task","programs","In Progress",2,
                        "Was running.",None,now,now
                    )
                )
                interrupted_id=int(cur.lastrowid)

                campus.set_workflow_run(
                    conn,
                    project_id,
                    state="Running",
                    current_task_id=interrupted_id,
                    last_error=None,
                )

            recovered=campus.reconcile_interrupted_workflows()
            assert recovered == [project_id]

            with campus.db() as conn:
                project=conn.execute(
                    "SELECT * FROM projects WHERE id=?",(project_id,)
                ).fetchone()
                completed=conn.execute(
                    "SELECT * FROM tasks WHERE id=?",(completed_id,)
                ).fetchone()
                interrupted=conn.execute(
                    "SELECT * FROM tasks WHERE id=?",(interrupted_id,)
                ).fetchone()
                run=conn.execute(
                    "SELECT * FROM workflow_runs WHERE project_id=?",(project_id,)
                ).fetchone()

            assert project["status"] == "Execution Interrupted"
            assert completed["status"] == "Completed"
            assert completed["result"] == "KEEP THIS RESULT"
            assert interrupted["status"] == "Blocked"
            assert "Campus restarted" in interrupted["result"]
            assert run["state"] == "Interrupted"
            assert run["current_task_id"] == interrupted_id
    finally:
        campus.DB_PATH=original


def test_v079_restart_does_not_break_human_review_gate():
    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Human Gate Test","Awaiting Execution Review",now,now)
                )
                project_id=int(cur.lastrowid)
                campus.set_workflow_run(
                    conn,
                    project_id,
                    state="Running",
                    current_task_id=None,
                    last_error=None,
                )

            recovered=campus.reconcile_interrupted_workflows()
            assert recovered == []

            with campus.db() as conn:
                project=conn.execute(
                    "SELECT status FROM projects WHERE id=?",(project_id,)
                ).fetchone()
                run=conn.execute(
                    "SELECT state FROM workflow_runs WHERE project_id=?",(project_id,)
                ).fetchone()

            assert project["status"] == "Awaiting Execution Review"
            assert run["state"] == "Awaiting Human Review"
    finally:
        campus.DB_PATH=original


def test_v079_repair_missing_and_duplicate_approval_gates():
    import json

    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                # Missing plan approval.
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Missing Plan Gate","Awaiting Approval",now,now)
                )
                plan_project=int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO chief_plans(
                        project_id,summary,success_criteria_json,questions_json,risk_notes_json,
                        provider,model,created_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        plan_project,"Recovered plan summary.","[]","[]","[]",
                        "gemini","fake-chief",now
                    )
                )

                # Missing final approval.
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Missing Final Gate","Awaiting Execution Review",now,now)
                )
                final_project=int(cur.lastrowid)
                cur=conn.execute(
                    """
                    INSERT INTO tasks(
                        project_id,title,owner_agent_id,status,sequence,brief,result,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        final_project,"Chief final review","chief","Completed",1,
                        "Review.","AI-generated — Chief Final Review",now,now
                    )
                )
                review_task=int(cur.lastrowid)
                artifact={
                    "review_title":"Recovered Review",
                    "executive_summary":"The package is ready for internal review.",
                    "approval_recommendation":"approve_internal"
                }
                conn.execute(
                    """
                    INSERT INTO chief_review_artifacts(
                        task_id,project_id,content_json,provider,model,attempt_count,created_at
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        review_task,final_project,json.dumps(artifact),
                        "gemini","fake-chief",1,now
                    )
                )

                # Duplicate pending final approvals.
                for _ in range(2):
                    conn.execute(
                        """
                        INSERT INTO approvals(
                            project_id,title,summary,status,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?)
                        """,
                        (
                            final_project,"Chief final review: Missing Final Gate",
                            "Duplicate.","Pending",now,now
                        )
                    )

            result=campus.repair_approval_invariants()
            assert result["repaired"] == 1
            assert result["superseded"] == 1

            with campus.db() as conn:
                plan_pending=conn.execute(
                    """
                    SELECT COUNT(*) FROM approvals
                    WHERE project_id=? AND status='Pending'
                      AND title LIKE 'Approve Chief''s plan:%'
                    """,
                    (plan_project,)
                ).fetchone()[0]
                final_pending=conn.execute(
                    """
                    SELECT COUNT(*) FROM approvals
                    WHERE project_id=? AND status='Pending'
                      AND title LIKE 'Chief final review:%'
                    """,
                    (final_project,)
                ).fetchone()[0]
                superseded=conn.execute(
                    """
                    SELECT COUNT(*) FROM approvals
                    WHERE project_id=? AND status='Superseded'
                    """,
                    (final_project,)
                ).fetchone()[0]

            assert plan_pending == 1
            assert final_pending == 1
            assert superseded == 1
    finally:
        campus.DB_PATH=original


def test_v079_resume_preserves_completed_tasks_and_finishes_unfinished():
    import asyncio

    original_db=campus.DB_PATH
    original_pause=campus.pause
    original_workflow=campus.workflow_task
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            campus.workflow_task=None
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Resume Test","Execution Interrupted",now,now)
                )
                project_id=int(cur.lastrowid)

                cur=conn.execute(
                    """
                    INSERT INTO tasks(
                        project_id,title,owner_agent_id,status,sequence,brief,result,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Already done","caretaker","Completed",1,
                        "Done.","DO NOT REPEAT",now,now
                    )
                )
                completed_id=int(cur.lastrowid)

                cur=conn.execute(
                    """
                    INSERT INTO tasks(
                        project_id,title,owner_agent_id,status,sequence,brief,result,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Retry this","caretaker","Blocked",2,
                        "Finish this.","Old interruption error",now,now
                    )
                )
                retry_id=int(cur.lastrowid)

                campus.set_workflow_run(
                    conn,
                    project_id,
                    state="Interrupted",
                    current_task_id=retry_id,
                    last_error="Test interruption.",
                )

            async def no_pause(seconds=0):
                return None
            campus.pause=no_pause

            async def run_test():
                result=await campus.api_project_resume(project_id)
                assert result["completed_tasks_preserved"] is True
                assert campus.workflow_task is not None
                await campus.workflow_task

            asyncio.run(run_test())

            with campus.db() as conn:
                completed=conn.execute(
                    "SELECT * FROM tasks WHERE id=?",(completed_id,)
                ).fetchone()
                retried=conn.execute(
                    "SELECT * FROM tasks WHERE id=?",(retry_id,)
                ).fetchone()
                project=conn.execute(
                    "SELECT * FROM projects WHERE id=?",(project_id,)
                ).fetchone()
                run=conn.execute(
                    "SELECT * FROM workflow_runs WHERE project_id=?",(project_id,)
                ).fetchone()
                pending=conn.execute(
                    """
                    SELECT COUNT(*) FROM approvals
                    WHERE project_id=? AND status='Pending'
                      AND title LIKE 'Chief final review:%'
                    """,
                    (project_id,)
                ).fetchone()[0]

            assert completed["status"] == "Completed"
            assert completed["result"] == "DO NOT REPEAT"
            assert retried["status"] == "Completed"
            assert "Simulated — Stewart — Land Steward" in retried["result"]
            assert project["status"] == "Awaiting Execution Review"
            assert run["state"] == "Awaiting Human Review"
            assert run["retry_count"] == 1
            assert pending == 1
    finally:
        campus.pause=original_pause
        campus.workflow_task=original_workflow
        campus.DB_PATH=original_db


def test_v079_final_approval_is_not_duplicated_on_refinalization():
    import asyncio

    original_db=campus.DB_PATH
    original_pause=campus.pause
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Duplicate Guard Test","Active",now,now)
                )
                project_id=int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO tasks(
                        project_id,title,owner_agent_id,status,sequence,brief,result,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Completed task","caretaker","Completed",1,
                        "Done.","Done.",now,now
                    )
                )

            async def no_pause(seconds=0):
                return None
            campus.pause=no_pause

            asyncio.run(campus.execute_approved_plan(project_id))
            asyncio.run(campus.execute_approved_plan(project_id,resume=True))

            with campus.db() as conn:
                pending=conn.execute(
                    """
                    SELECT COUNT(*) FROM approvals
                    WHERE project_id=? AND status='Pending'
                      AND title LIKE 'Chief final review:%'
                    """,
                    (project_id,)
                ).fetchone()[0]

            assert pending == 1
    finally:
        campus.pause=original_pause
        campus.DB_PATH=original_db


def test_v079_recovery_ui_and_manifest():
    import json

    index=(ROOT/"static/index.html").read_text(encoding="utf-8")
    js=(ROOT/"static/js/app.js").read_text(encoding="utf-8")
    css=(ROOT/"static/css/world.css").read_text(encoding="utf-8")
    app_text=(ROOT/"app.py").read_text(encoding="utf-8")

    assert LIVE_SHELL_LABEL in index
    assert 'id="system-health"' in index
    assert "Retry / Resume Workflow" in js
    assert "data-retry-project" in js
    assert "function retryProject(projectId)" in js
    assert "workflow_runs" in js
    assert "system_health" in js
    assert ".execution-state.interrupted" in css
    assert ".recovery-button" in css

    assert "def reconcile_interrupted_workflows()" in app_text
    assert "def repair_approval_invariants()" in app_text
    assert '@app.post("/api/projects/{project_id}/resume")' in app_text
    assert "preserving completed work" in app_text

    data=json.loads(
        (ROOT/"static/assets/asset-manifest.json").read_text(encoding="utf-8")
    )
    assert data["build"] == LIVE_BUILD
    recovery=data["ai_runtime"]["stabilization_recovery"]
    assert recovery["enabled"] is True
    assert recovery["schema_version"] == LIVE_VERSION
    assert recovery["explicit_human_retry_required"] is True
    assert recovery["preserve_completed_tasks_on_retry"] is True
    assert recovery["duplicate_final_approval_protection"] is True
    assert recovery["startup_missing_approval_repair"] is True
    assert recovery["automatic_retry"] is False


def test_v080_chief_plan_adds_expected_deliverables_without_extra_call():
    from agents.chief_of_staff import normalize_plan

    plan=normalize_plan({
        "project_title":"Workshop Test",
        "summary":"Build a workshop.",
        "success_criteria":["Usable class"],
        "tasks":[
            {"title":"Research","owner":"research","brief":"Research it."},
            {"title":"Build","owner":"programs","brief":"Build it."},
            {"title":"Review","owner":"chief","brief":"Review it."},
        ],
        "questions_for_executive":[],
        "risk_notes":[],
    },"Build a workshop.")

    types={item["type"] for item in plan["expected_deliverables"]}
    assert "research_brief" in types
    assert "verification_checklist" in types
    assert "program_plan" in types
    assert "facilitator_guide" in types
    assert "materials_list" in types
    assert "participant_handout" in types
    assert "executive_summary" in types


def test_v080_schema_and_expected_deliverables_migration():
    import sqlite3

    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"

            # Simulate the old chief_plans schema before init_db runs.
            conn=sqlite3.connect(campus.DB_PATH)
            conn.execute(
                """
                CREATE TABLE chief_plans(
                    project_id INTEGER PRIMARY KEY,
                    summary TEXT NOT NULL,
                    success_criteria_json TEXT NOT NULL,
                    questions_json TEXT NOT NULL,
                    risk_notes_json TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
            conn.close()

            campus.init_db()

            with campus.db() as conn:
                tables={
                    row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                chief_columns={
                    row[1] for row in conn.execute(
                        "PRAGMA table_info(chief_plans)"
                    ).fetchall()
                }
                deliverable_columns={
                    row[1] for row in conn.execute(
                        "PRAGMA table_info(deliverables)"
                    ).fetchall()
                }
                health=campus.system_health(conn)

            assert "deliverables" in tables
            assert "expected_deliverables_json" in chief_columns
            assert {
                "project_id","source_task_id","deliverable_key","deliverable_type",
                "title","status","content_md","version","verification_json"
            }.issubset(deliverable_columns)
            assert health["ok"] is True
            assert health["schema_version"] == LIVE_VERSION
    finally:
        campus.DB_PATH=original


def test_v080_research_artifact_materializes_outputs_locally():
    import json

    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Research Outputs","Active",now,now)
                )
                project_id=int(cur.lastrowid)
                cur=conn.execute(
                    """
                    INSERT INTO tasks(
                        project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (project_id,"Research it","research","Completed",1,"Research.",now,now)
                )
                task_id=int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO chief_plans(
                        project_id,summary,success_criteria_json,questions_json,risk_notes_json,
                        expected_deliverables_json,provider,model,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Summary","[]","[]","[]",
                        json.dumps([
                            {"type":"research_brief","title":"My Research Brief","purpose":"Research"},
                            {"type":"verification_checklist","title":"My Verify List","purpose":"Verify"},
                        ]),
                        "gemini","fake",now
                    )
                )
                project=conn.execute("SELECT * FROM projects WHERE id=?",(project_id,)).fetchone()
                task=conn.execute("SELECT * FROM tasks WHERE id=?",(task_id,)).fetchone()

                before=conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]
                ids=campus.materialize_research_deliverables(
                    conn,
                    project=project,
                    task=task,
                    artifact={
                        "executive_summary":"Research summary.",
                        "findings":["Finding A"],
                        "practical_recommendations":["Recommendation A"],
                        "uncertainties":["Uncertain A"],
                        "verification_needed":["Verify A"],
                        "handoff_note":"Handoff."
                    },
                    provider="gemini",
                    model="fake-research"
                )
                after=conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]
                rows=conn.execute(
                    "SELECT * FROM deliverables WHERE project_id=? ORDER BY deliverable_type",
                    (project_id,)
                ).fetchall()

            assert len(ids) == 2
            assert before == after == 0
            assert {row["deliverable_type"] for row in rows} == {
                "research_brief","verification_checklist"
            }
            assert any(row["title"] == "My Research Brief" for row in rows)
            verify=next(row for row in rows if row["deliverable_type"]=="verification_checklist")
            assert verify["status"] == "Verify First"
            assert "Verify A" in verify["content_md"]
    finally:
        campus.DB_PATH=original


def test_v080_programs_artifact_materializes_four_useful_outputs():
    import json

    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Class Outputs","Active",now,now)
                )
                project_id=int(cur.lastrowid)
                cur=conn.execute(
                    """
                    INSERT INTO tasks(
                        project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (project_id,"Build class","programs","Completed",1,"Build class.",now,now)
                )
                task_id=int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO chief_plans(
                        project_id,summary,success_criteria_json,questions_json,risk_notes_json,
                        expected_deliverables_json,provider,model,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Summary","[]","[]","[]",
                        json.dumps([
                            {"type":"lesson_plan","title":"45-Minute Class Plan","purpose":"Teach"},
                            {"type":"facilitator_guide","title":"Instructor Guide","purpose":"Guide"},
                            {"type":"materials_list","title":"Supplies","purpose":"Prepare"},
                            {"type":"participant_handout","title":"Take-Home Handout","purpose":"Share"},
                        ]),
                        "gemini","fake",now
                    )
                )
                project=conn.execute("SELECT * FROM projects WHERE id=?",(project_id,)).fetchone()
                task=conn.execute("SELECT * FROM tasks WHERE id=?",(task_id,)).fetchone()

                before=conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]
                campus.materialize_programs_deliverables(
                    conn,
                    project=project,
                    task=task,
                    artifact={
                        "deliverable_title":"Class",
                        "program_summary":"A useful class.",
                        "audience":"All ages",
                        "duration_minutes":45,
                        "objectives":["Learn A"],
                        "run_of_show":[{
                            "minutes":45,
                            "segment":"Workshop",
                            "purpose":"Teach A",
                            "facilitator_action":"Demonstrate A."
                        }],
                        "materials":["Paper"],
                        "participant_activities":["Practice A"],
                        "facilitator_notes":["Keep it hands-on."],
                        "handout_or_resource_ideas":["Checklist"],
                        "research_integration":["Used research."],
                        "verification_flags":["Verify archival guidance."],
                        "handoff_note":"Ready."
                    },
                    provider="openai",
                    model="fake-terra"
                )
                after=conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]
                outputs=conn.execute(
                    "SELECT * FROM deliverables WHERE project_id=? ORDER BY deliverable_type",
                    (project_id,)
                ).fetchall()

            assert before == after == 0
            assert len(outputs) == 4
            types={row["deliverable_type"] for row in outputs}
            assert types == {
                "lesson_plan","facilitator_guide","materials_list","participant_handout"
            }
            assert any(row["title"]=="45-Minute Class Plan" for row in outputs)
            handout=next(row for row in outputs if row["deliverable_type"]=="participant_handout")
            assert handout["status"] == "Verify First"
            assert "Take-Home Handout" in handout["content_md"]
    finally:
        campus.DB_PATH=original


def test_v080_chief_review_receives_and_reviews_deliverables():
    import json
    from ai.provider import GenerationResult
    from agents.chief_review import run_chief_review

    seen={"prompt":""}

    class FakeChief:
        def generate_text(self,prompt,max_output_tokens=120):
            seen["prompt"]=prompt
            text=json.dumps({
                "review_title":"Output Review",
                "executive_summary":"The package is usable.",
                "approval_recommendation":"approve_internal",
                "success_criteria_review":[{
                    "criterion":"Make a class",
                    "status":"met",
                    "evidence":"The lesson plan exists."
                }],
                "deliverable_review":[{
                    "deliverable_key":"lesson_plan:task:2",
                    "deliverable":"45-Minute Class Plan",
                    "status":"ready",
                    "note":"Ready for internal approval."
                }],
                "research_programs_alignment":[],
                "gaps_or_conflicts":[],
                "verification_before_public_use":[],
                "recommended_revisions":[],
                "executive_decisions_needed":[],
                "final_package_summary":"One lesson plan.",
                "handoff_note":"Review outputs."
            })
            return GenerationResult("gemini","fake-chief",text,len(prompt),len(text))

    result=run_chief_review(
        FakeChief(),
        project_title="Class",
        project_summary="Build class.",
        task_title="Final review",
        task_brief="Review it.",
        success_criteria=["Make a class"],
        deliverables=[{
            "deliverable_key":"lesson_plan:task:2",
            "deliverable_type":"lesson_plan",
            "title":"45-Minute Class Plan",
            "purpose":"Teach",
            "status":"Draft",
            "content_excerpt":"# Class Plan\nUseful content.",
            "verification_items":[],
            "created_by":"Programs"
        }],
    )

    assert "CURRENT PROJECT DELIVERABLES" in seen["prompt"]
    assert "45-Minute Class Plan" in seen["prompt"]
    assert result.artifact["deliverable_review"][0]["status"] == "ready"
    assert "DELIVERABLE REVIEW" in result.rendered_text


def test_v080_chief_review_updates_output_readiness():
    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Review Outputs","Active",now,now)
                )
                project_id=int(cur.lastrowid)
                ready_id=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=None,
                    deliverable_type="program_plan",title="Plan",purpose="Plan",
                    content_md="# Plan",created_by="Programs",provider="openai",model="fake"
                )
                verify_id=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=None,
                    deliverable_type="participant_handout",title="Handout",purpose="Handout",
                    content_md="# Handout",created_by="Programs",provider="openai",model="fake",
                    verification_items=["Verify this"]
                )

                ready=conn.execute("SELECT * FROM deliverables WHERE id=?",(ready_id,)).fetchone()
                verify=conn.execute("SELECT * FROM deliverables WHERE id=?",(verify_id,)).fetchone()

                campus.apply_chief_deliverable_review(
                    conn,
                    project_id=project_id,
                    artifact={
                        "approval_recommendation":"approve_internal",
                        "deliverable_review":[
                            {
                                "deliverable_key":ready["deliverable_key"],
                                "deliverable":"Plan",
                                "status":"ready",
                                "note":"Ready."
                            },
                            {
                                "deliverable_key":verify["deliverable_key"],
                                "deliverable":"Handout",
                                "status":"needs_verification",
                                "note":"Verify first."
                            }
                        ]
                    }
                )

                ready_after=conn.execute("SELECT * FROM deliverables WHERE id=?",(ready_id,)).fetchone()
                verify_after=conn.execute("SELECT * FROM deliverables WHERE id=?",(verify_id,)).fetchone()

            assert ready_after["status"] == "Approval Ready"
            assert ready_after["chief_review_status"] == "ready"
            assert verify_after["status"] == "Verify First"
            assert verify_after["chief_review_status"] == "needs_verification"
            assert verify_after["chief_review_note"] == "Verify first."
    finally:
        campus.DB_PATH=original


def test_v080_final_human_approval_marks_outputs_approved():
    import asyncio

    original=campus.DB_PATH
    original_workflow=campus.workflow_task
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            campus.workflow_task=None
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Approve Outputs","Awaiting Execution Review",now,now)
                )
                project_id=int(cur.lastrowid)
                output_id=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=None,
                    deliverable_type="executive_summary",title="Executive Summary",
                    purpose="Summary",content_md="# Summary",created_by="Chief of Staff",
                    provider="gemini",model="fake",status="Approval Ready"
                )
                cur=conn.execute(
                    """
                    INSERT INTO approvals(project_id,title,summary,status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Chief final review: Approve Outputs",
                        "Ready.","Pending",now,now
                    )
                )
                approval_id=int(cur.lastrowid)

            result=asyncio.run(
                campus.api_approval_decide(
                    approval_id,
                    campus.ApprovalDecision(decision="approve",note="")
                )
            )
            assert result["project_completed"] is True

            with campus.db() as conn:
                output=conn.execute("SELECT * FROM deliverables WHERE id=?",(output_id,)).fetchone()
                project=conn.execute("SELECT * FROM projects WHERE id=?",(project_id,)).fetchone()

            assert output["status"] == "Approved"
            assert project["status"] == "Completed"
    finally:
        campus.workflow_task=original_workflow
        campus.DB_PATH=original


def test_v080_request_changes_preserves_and_marks_outputs():
    import asyncio

    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Revise Outputs","Awaiting Execution Review",now,now)
                )
                project_id=int(cur.lastrowid)
                output_id=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=None,
                    deliverable_type="program_plan",title="Program",
                    purpose="Program",content_md="# Program\nKeep this content.",
                    created_by="Programs",provider="openai",model="fake",
                    status="Approval Ready"
                )
                cur=conn.execute(
                    """
                    INSERT INTO approvals(project_id,title,summary,status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Chief final review: Revise Outputs",
                        "Review.","Pending",now,now
                    )
                )
                approval_id=int(cur.lastrowid)

            asyncio.run(
                campus.api_approval_decide(
                    approval_id,
                    campus.ApprovalDecision(decision="changes",note="Make it simpler.")
                )
            )

            with campus.db() as conn:
                output=conn.execute("SELECT * FROM deliverables WHERE id=?",(output_id,)).fetchone()
                project=conn.execute("SELECT * FROM projects WHERE id=?",(project_id,)).fetchone()

            assert output["status"] == "Revision Review"
            assert "Keep this content." in output["content_md"]
            assert project["status"] == "Needs Revision"
    finally:
        campus.DB_PATH=original


def test_v080_project_outputs_end_to_end_uses_existing_three_ai_calls():
    import asyncio
    import json
    from ai.provider import GenerationResult

    original_db=campus.DB_PATH
    original_pause=campus.pause
    original_get_role_provider=campus.get_role_provider

    class FakeProvider:
        def generate_text(self,prompt,max_output_tokens=120):
            if "APPROVED RESEARCH TASK" in prompt:
                text=json.dumps({
                    "executive_summary":"Preservation research.",
                    "findings":["Use redundant copies."],
                    "practical_recommendations":["Keep physical originals protected."],
                    "uncertainties":[],
                    "verification_needed":["Verify current archival guidance."],
                    "handoff_note":"Programs can build the class."
                })
                return GenerationResult("gemini","fake-research",text,len(prompt),len(text))

            if "APPROVED PROGRAMS TASK" in prompt:
                text=json.dumps({
                    "deliverable_title":"Preserve What Matters",
                    "program_summary":"A 45-minute all-ages class.",
                    "audience":"All ages",
                    "duration_minutes":45,
                    "objectives":["Understand physical and digital preservation."],
                    "run_of_show":[{
                        "minutes":45,"segment":"Class","purpose":"Teach preservation",
                        "facilitator_action":"Demonstrate and discuss."
                    }],
                    "materials":["Sample folder"],
                    "participant_activities":["Create a preservation checklist."],
                    "facilitator_notes":["Use plain language."],
                    "handout_or_resource_ideas":["Take-home checklist"],
                    "research_integration":["Uses redundant-copy guidance."],
                    "verification_flags":["Verify current archival guidance."],
                    "handoff_note":"Ready for Chief review."
                })
                return GenerationResult("openai","fake-programs",text,len(prompt),len(text))

            if "FINAL CHIEF TASK:" in prompt:
                assert "CURRENT PROJECT DELIVERABLES" in prompt
                assert "Participant Handout" in prompt
                text=json.dumps({
                    "review_title":"Class Package Review",
                    "executive_summary":"The project produced a complete internal class package.",
                    "approval_recommendation":"approve_internal",
                    "success_criteria_review":[{
                        "criterion":"Create the class package",
                        "status":"met",
                        "evidence":"Programs outputs are present."
                    }],
                    "deliverable_review":[],
                    "research_programs_alignment":["Programs used Research."],
                    "gaps_or_conflicts":[],
                    "verification_before_public_use":["Verify current archival guidance."],
                    "recommended_revisions":[],
                    "executive_decisions_needed":["Approve the internal package."],
                    "final_package_summary":"Class plan, guide, materials, handout, research, verification, and executive summary.",
                    "handoff_note":"Review Outputs."
                })
                return GenerationResult("gemini","fake-chief",text,len(prompt),len(text))

            raise AssertionError("Unexpected prompt")

    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Preservation Class","Active",now,now)
                )
                project_id=int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO chief_plans(
                        project_id,summary,success_criteria_json,questions_json,risk_notes_json,
                        expected_deliverables_json,provider,model,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Build a class package.",
                        json.dumps(["Create the class package"]),"[]","[]",
                        json.dumps([
                            {"type":"research_brief","title":"Research Brief","purpose":"Research"},
                            {"type":"verification_checklist","title":"Verification Checklist","purpose":"Verify"},
                            {"type":"lesson_plan","title":"45-Minute Class Plan","purpose":"Teach"},
                            {"type":"facilitator_guide","title":"Facilitator Guide","purpose":"Guide"},
                            {"type":"materials_list","title":"Materials List","purpose":"Prepare"},
                            {"type":"participant_handout","title":"Participant Handout","purpose":"Share"},
                            {"type":"executive_summary","title":"Executive Summary","purpose":"Decide"},
                        ]),
                        "gemini","fake",now
                    )
                )
                for seq,title,owner,brief in [
                    (1,"Research preservation","research","Research."),
                    (2,"Build class","programs","Build class."),
                    (3,"Review package","chief","Review all outputs."),
                ]:
                    conn.execute(
                        """
                        INSERT INTO tasks(
                            project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?)
                        """,
                        (project_id,title,owner,"Waiting",seq,brief,now,now)
                    )

            async def no_pause(seconds=0):
                return None

            campus.pause=no_pause
            campus.get_role_provider=lambda role: FakeProvider()
            asyncio.run(campus.execute_approved_plan(project_id))

            with campus.db() as conn:
                outputs=conn.execute(
                    "SELECT * FROM deliverables WHERE project_id=? ORDER BY id",
                    (project_id,)
                ).fetchall()
                calls=conn.execute(
                    """
                    SELECT operation,status FROM ai_calls
                    WHERE project_id=? AND status='Success'
                    ORDER BY id
                    """,
                    (project_id,)
                ).fetchall()
                project=conn.execute(
                    "SELECT * FROM projects WHERE id=?",(project_id,)
                ).fetchone()

            types={row["deliverable_type"] for row in outputs}
            assert {
                "research_brief","verification_checklist","lesson_plan",
                "facilitator_guide","materials_list","participant_handout",
                "executive_summary"
            }.issubset(types)
            assert len(calls) == 3
            assert [row["operation"] for row in calls] == [
                "research_task","programs_task","chief_final_review"
            ]
            assert project["status"] == "Awaiting Execution Review"
            assert all(row["status"] in {
                "Approval Ready","Verify First","Needs Revision"
            } for row in outputs)
    finally:
        campus.pause=original_pause
        campus.get_role_provider=original_get_role_provider
        campus.DB_PATH=original_db


def test_v080_outputs_ui_reader_exports_and_tabs():
    index=(ROOT/"static/index.html").read_text(encoding="utf-8")
    js=(ROOT/"static/js/app.js").read_text(encoding="utf-8")
    css=(ROOT/"static/css/world.css").read_text(encoding="utf-8")

    assert LIVE_SHELL_LABEL in index
    assert 'id="overview-outputs"' in index
    assert 'id="deliverable-modal"' in index
    assert "Download .md" in index
    assert "Download .txt" in index
    assert "Print / Save PDF" in index

    assert "Overview" in js
    assert "Outputs" in js
    assert "Tasks" in js
    assert "Notes" in js
    assert "History" in js
    assert "function openDeliverable(id)" in js
    assert "function renderSimpleMarkdown" in js
    assert "navigator.clipboard.writeText" in js
    assert "downloadActiveDeliverable('md')" in js
    assert "downloadActiveDeliverable('txt')" in js
    assert "window.print()" in js
    assert "data-open-deliverable" in js
    assert "expected output types covered" in js

    assert ".deliverable-modal" in css
    assert ".deliverable-card" in css
    assert ".project-tabs" in css
    assert "@media print" in css


def test_v080_manifest_project_outputs():
    import json

    data=json.loads(
        (ROOT/"static/assets/asset-manifest.json").read_text(encoding="utf-8")
    )
    assert data["build"] == LIVE_BUILD
    assert data["ai_runtime"]["stabilization_recovery"]["schema_version"] == LIVE_VERSION

    outputs=data["ai_runtime"]["project_outputs"]
    assert outputs["enabled"] is True
    assert outputs["deliverables_table"] == "deliverables"
    assert outputs["chief_expected_deliverables"] is True
    assert outputs["local_assembly_without_extra_ai_calls"] is True
    assert outputs["chief_reviews_actual_deliverables"] is True
    assert outputs["versions_enabled"] is True
    assert outputs["initial_version"] == 1
    assert outputs["human_final_approval_marks_outputs_approved"] is True
    assert outputs["additional_formatting_ai_calls"] is False
    assert outputs["browser_exports"] == ["markdown","text","print_save_pdf"]


def test_v081_chief_revision_planner_repairs_and_filters_ids():
    import json
    from ai.provider import GenerationResult
    from agents.chief_revision import run_chief_revision_plan

    class FakeChief:
        def __init__(self):
            self.calls=0
        def generate_text(self,prompt,max_output_tokens=1600):
            self.calls+=1
            if self.calls==1:
                text="not-json"
            else:
                text=json.dumps({
                    "revision_summary":"Revise only the handout.",
                    "task_revisions":[
                        {
                            "task_id":2,
                            "reason":"Programs owns the handout.",
                            "revision_brief":"Simplify the handout for younger participants."
                        },
                        {
                            "task_id":999,
                            "reason":"Invented",
                            "revision_brief":"Should be filtered."
                        }
                    ],
                    "deliverable_revisions":[
                        {
                            "deliverable_key":"participant_handout:task:2",
                            "reason":"Needs simpler wording."
                        },
                        {
                            "deliverable_key":"invented:key",
                            "reason":"Should be filtered."
                        }
                    ],
                    "preserve_deliverable_keys":["research_brief:task:1"],
                    "questions_for_executive":[]
                })
            return GenerationResult(
                provider="gemini",
                model="fake-chief",
                text=text,
                input_chars=len(prompt),
                output_chars=len(text),
            )

    provider=FakeChief()
    result=run_chief_revision_plan(
        provider,
        project_title="Class",
        project_summary="Build class.",
        success_criteria=["Usable package"],
        human_revision_request="Make only the handout simpler.",
        tasks=[
            {"task_id":1,"owner":"research","title":"Research"},
            {"task_id":2,"owner":"programs","title":"Programs"},
            {"task_id":3,"owner":"chief","title":"Review"},
        ],
        deliverables=[
            {
                "deliverable_key":"research_brief:task:1",
                "title":"Research Brief"
            },
            {
                "deliverable_key":"participant_handout:task:2",
                "title":"Handout"
            },
        ],
        previous_chief_review={},
    )

    assert result.attempt_count == 2
    assert provider.calls == 2
    assert [x["task_id"] for x in result.plan["task_revisions"]] == [2]
    assert [x["deliverable_key"] for x in result.plan["deliverable_revisions"]] == [
        "participant_handout:task:2"
    ]
    assert result.plan["preserve_deliverable_keys"] == ["research_brief:task:1"]


def test_v081_final_changes_creates_durable_revision_request():
    import asyncio

    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Revision Request Test","Awaiting Execution Review",now,now)
                )
                project_id=int(cur.lastrowid)
                output_id=campus.upsert_deliverable(
                    conn,
                    project_id=project_id,
                    source_task_id=None,
                    deliverable_type="program_plan",
                    title="Program Plan",
                    purpose="Plan",
                    content_md="# Version 1",
                    created_by="Programs",
                    provider="openai",
                    model="fake",
                    status="Approval Ready",
                )
                cur=conn.execute(
                    """
                    INSERT INTO approvals(
                        project_id,title,summary,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        project_id,
                        "Chief final review: Revision Request Test",
                        "Ready for review.",
                        "Pending",
                        now,
                        now,
                    )
                )
                approval_id=int(cur.lastrowid)

            result=asyncio.run(
                campus.api_approval_decide(
                    approval_id,
                    campus.ApprovalDecision(
                        decision="changes",
                        note="Make the participant material easier for children."
                    ),
                )
            )
            assert result["status"] == "Changes Requested"

            with campus.db() as conn:
                request=conn.execute(
                    "SELECT * FROM revision_requests WHERE project_id=?",
                    (project_id,),
                ).fetchone()
                output=conn.execute(
                    "SELECT * FROM deliverables WHERE id=?",
                    (output_id,),
                ).fetchone()
                project=conn.execute(
                    "SELECT status FROM projects WHERE id=?",
                    (project_id,),
                ).fetchone()

            assert request["status"] == "Requested"
            assert "easier for children" in request["request_text"]
            assert output["status"] == "Revision Review"
            assert output["version"] == 1
            assert output["content_md"] == "# Version 1"
            assert project["status"] == "Needs Revision"
    finally:
        campus.DB_PATH=original


def test_v081_real_chief_revision_plan_creates_second_human_gate():
    import asyncio
    import json
    from ai.provider import GenerationResult

    original_db=campus.DB_PATH
    original_provider=campus.get_role_provider
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Selective Revision Test","Needs Revision",now,now)
                )
                project_id=int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO chief_plans(
                        project_id,summary,success_criteria_json,questions_json,risk_notes_json,
                        expected_deliverables_json,provider,model,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Build a class.",json.dumps(["Useful class"]),
                        "[]","[]","[]","gemini","fake",now
                    )
                )
                task_ids={}
                for seq,title,owner in [
                    (1,"Research","research"),
                    (2,"Build class","programs"),
                    (3,"Final review","chief"),
                ]:
                    cur=conn.execute(
                        """
                        INSERT INTO tasks(
                            project_id,title,owner_agent_id,status,sequence,brief,result,
                            created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            project_id,title,owner,"Completed",seq,title,
                            f"Old {title} result",now,now
                        )
                    )
                    task_ids[owner]=int(cur.lastrowid)

                research_id=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=task_ids["research"],
                    deliverable_type="research_brief",title="Research Brief",
                    purpose="Research",content_md="# Research v1",created_by="Research",
                    provider="gemini",model="fake",status="Revision Review"
                )
                handout_id=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=task_ids["programs"],
                    deliverable_type="participant_handout",title="Participant Handout",
                    purpose="Handout",content_md="# Handout v1",created_by="Programs",
                    provider="openai",model="fake",status="Revision Review"
                )
                conn.execute(
                    """
                    INSERT INTO revision_requests(
                        project_id,source_approval_id,request_text,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        project_id,None,
                        "Make only the participant handout easier for children.",
                        "Requested",now,now
                    )
                )

            class FakeChief:
                def generate_text(self,prompt,max_output_tokens=1600):
                    assert "HUMAN REVISION INSTRUCTION" in prompt
                    assert "Participant Handout" in prompt
                    text=json.dumps({
                        "revision_summary":"Revise only the participant handout.",
                        "task_revisions":[{
                            "task_id":task_ids["programs"],
                            "reason":"Programs owns the handout.",
                            "revision_brief":"Simplify the participant handout for children."
                        }],
                        "deliverable_revisions":[{
                            "deliverable_key":f"participant_handout:task:{task_ids['programs']}",
                            "reason":"Needs simpler language."
                        }],
                        "preserve_deliverable_keys":[
                            f"research_brief:task:{task_ids['research']}"
                        ],
                        "questions_for_executive":[]
                    })
                    return GenerationResult(
                        "gemini","fake-chief",text,len(prompt),len(text)
                    )

            campus.get_role_provider=lambda role: FakeChief()
            result=asyncio.run(campus.api_revision_plan(project_id))
            assert result["status"] == "awaiting_revision_approval"
            assert result["selected_task_count"] == 1
            assert result["selected_output_count"] == 1

            with campus.db() as conn:
                project=conn.execute(
                    "SELECT status FROM projects WHERE id=?",(project_id,)
                ).fetchone()
                plan=conn.execute(
                    "SELECT * FROM revision_plans WHERE project_id=?",(project_id,)
                ).fetchone()
                approval=conn.execute(
                    """
                    SELECT * FROM approvals
                    WHERE project_id=? AND status='Pending'
                      AND title LIKE 'Approve revision plan:%'
                    """,
                    (project_id,)
                ).fetchone()
                tasks=conn.execute(
                    "SELECT owner_agent_id,status FROM tasks WHERE project_id=?",
                    (project_id,)
                ).fetchall()
                outputs=conn.execute(
                    "SELECT id,status FROM deliverables WHERE project_id=?",
                    (project_id,)
                ).fetchall()
                calls=conn.execute(
                    "SELECT * FROM ai_calls WHERE project_id=? AND operation='chief_revision_plan'",
                    (project_id,)
                ).fetchall()

            assert project["status"] == "Awaiting Revision Approval"
            assert plan["status"] == "Awaiting Approval"
            assert approval is not None
            assert all(row["status"]=="Completed" for row in tasks)
            assert {row["status"] for row in outputs} == {"Revision Review"}
            assert len(calls) == 1
            assert calls[0]["status"] == "Success"
    finally:
        campus.get_role_provider=original_provider
        campus.DB_PATH=original_db


def test_v081_revision_plan_approval_reopens_only_selected_work():
    import asyncio
    import json

    original_db=campus.DB_PATH
    original_workflow=campus.workflow_task
    original_execute=campus.execute_approved_plan
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            campus.workflow_task=None
            now=campus.utc_now()
            captured={}

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Approval Scope Test","Awaiting Revision Approval",now,now)
                )
                project_id=int(cur.lastrowid)

                task_ids={}
                for seq,title,owner in [
                    (1,"Research","research"),
                    (2,"Programs","programs"),
                    (3,"Chief Review","chief"),
                ]:
                    cur=conn.execute(
                        """
                        INSERT INTO tasks(
                            project_id,title,owner_agent_id,status,sequence,brief,result,
                            created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            project_id,title,owner,"Completed",seq,title,
                            f"Old {title}",now,now
                        )
                    )
                    task_ids[owner]=int(cur.lastrowid)

                research_out=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=task_ids["research"],
                    deliverable_type="research_brief",title="Research Brief",
                    purpose="Research",content_md="# Research v1",created_by="Research",
                    provider="gemini",model="fake",status="Revision Review"
                )
                handout_out=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=task_ids["programs"],
                    deliverable_type="participant_handout",title="Handout",
                    purpose="Handout",content_md="# Handout v1",created_by="Programs",
                    provider="openai",model="fake",status="Revision Review"
                )
                exec_out=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=task_ids["chief"],
                    deliverable_type="executive_summary",title="Executive Summary",
                    purpose="Summary",content_md="# Summary v1",created_by="Chief of Staff",
                    provider="gemini",model="fake",status="Revision Review"
                )

                cur=conn.execute(
                    """
                    INSERT INTO revision_requests(
                        project_id,source_approval_id,request_text,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (project_id,None,"Revise handout.","Awaiting Approval",now,now)
                )
                request_id=int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO revision_plans(
                        project_id,request_id,revision_number,summary,task_revisions_json,
                        deliverable_revisions_json,preserve_keys_json,questions_json,
                        provider,model,attempt_count,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,request_id,1,"Handout only.",
                        json.dumps([{
                            "task_id":task_ids["programs"],
                            "reason":"Revise handout.",
                            "revision_brief":"Make handout simpler."
                        }]),
                        json.dumps([{
                            "deliverable_key":f"participant_handout:task:{task_ids['programs']}",
                            "reason":"Simplify."
                        }]),
                        json.dumps([f"research_brief:task:{task_ids['research']}"]),
                        "[]","gemini","fake-chief",1,"Awaiting Approval",now,now
                    )
                )
                cur=conn.execute(
                    """
                    INSERT INTO approvals(
                        project_id,title,summary,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Approve revision plan: Approval Scope Test — Revision 1",
                        "Selective revision.","Pending",now,now
                    )
                )
                approval_id=int(cur.lastrowid)

            async def fake_execute(project_id_arg, *, resume=False, revision=False):
                captured["project_id"]=project_id_arg
                captured["resume"]=resume
                captured["revision"]=revision

            campus.execute_approved_plan=fake_execute

            async def run_test():
                result=await campus.api_approval_decide(
                    approval_id,
                    campus.ApprovalDecision(decision="approve",note="")
                )
                assert result["revision_execution_started"] is True
                await campus.workflow_task
            asyncio.run(run_test())

            with campus.db() as conn:
                research=conn.execute(
                    "SELECT status,result FROM tasks WHERE id=?",(task_ids["research"],)
                ).fetchone()
                programs=conn.execute(
                    "SELECT status,result FROM tasks WHERE id=?",(task_ids["programs"],)
                ).fetchone()
                chief=conn.execute(
                    "SELECT status FROM tasks WHERE id=?",(task_ids["chief"],)
                ).fetchone()
                research_output=conn.execute(
                    "SELECT status FROM deliverables WHERE id=?",(research_out,)
                ).fetchone()
                handout_output=conn.execute(
                    "SELECT status FROM deliverables WHERE id=?",(handout_out,)
                ).fetchone()
                exec_output=conn.execute(
                    "SELECT status FROM deliverables WHERE id=?",(exec_out,)
                ).fetchone()
                plan=conn.execute(
                    "SELECT status FROM revision_plans WHERE project_id=?",(project_id,)
                ).fetchone()

            assert captured == {
                "project_id":project_id,"resume":False,"revision":True
            }
            assert research["status"] == "Completed"
            assert research["result"] == "Old Research"
            assert programs["status"] == "Waiting"
            assert programs["result"] == "Old Programs"
            assert chief["status"] == "Waiting"
            assert research_output["status"] == "Preserved"
            assert handout_output["status"] == "Revision Queued"
            assert exec_output["status"] == "Revision Queued"
            assert plan["status"] == "Executing"
    finally:
        campus.execute_approved_plan=original_execute
        campus.workflow_task=original_workflow
        campus.DB_PATH=original_db


def test_v081_revision_aware_upsert_versions_selected_only():
    import json

    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Version Test","Active",now,now)
                )
                project_id=int(cur.lastrowid)
                cur=conn.execute(
                    """
                    INSERT INTO tasks(
                        project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (project_id,"Programs","programs","Waiting",1,"Revise.",now,now)
                )
                task_id=int(cur.lastrowid)

                selected_v1=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=task_id,
                    deliverable_type="participant_handout",title="Handout",
                    purpose="Handout",content_md="# Handout v1",created_by="Programs",
                    provider="openai",model="fake",status="Revision Review"
                )
                preserved_v1=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=task_id,
                    deliverable_type="materials_list",title="Materials",
                    purpose="Materials",content_md="# Materials v1",created_by="Programs",
                    provider="openai",model="fake",status="Revision Review"
                )

                cur=conn.execute(
                    """
                    INSERT INTO revision_requests(
                        project_id,source_approval_id,request_text,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (project_id,None,"Revise handout.","Executing",now,now)
                )
                request_id=int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO revision_plans(
                        project_id,request_id,revision_number,summary,task_revisions_json,
                        deliverable_revisions_json,preserve_keys_json,questions_json,
                        provider,model,attempt_count,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,request_id,1,"Handout only.","[]","[]","[]","[]",
                        "gemini","fake",1,"Executing",now,now
                    )
                )
                conn.execute(
                    "UPDATE deliverables SET status='Revision Queued' WHERE id=?",
                    (selected_v1,)
                )
                conn.execute(
                    "UPDATE deliverables SET status='Preserved' WHERE id=?",
                    (preserved_v1,)
                )

                selected_v2=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=task_id,
                    deliverable_type="participant_handout",title="Handout",
                    purpose="Handout",content_md="# Handout v2",created_by="Programs",
                    provider="openai",model="fake",status="Draft"
                )
                preserved_result=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=task_id,
                    deliverable_type="materials_list",title="Materials",
                    purpose="Materials",content_md="# SHOULD NOT REPLACE",created_by="Programs",
                    provider="openai",model="fake",status="Draft"
                )

                selected_rows=conn.execute(
                    """
                    SELECT version,status,content_md
                    FROM deliverables
                    WHERE project_id=? AND deliverable_type='participant_handout'
                    ORDER BY version
                    """,
                    (project_id,)
                ).fetchall()
                preserved=conn.execute(
                    "SELECT * FROM deliverables WHERE id=?",(preserved_v1,)
                ).fetchone()

            assert selected_v2 != selected_v1
            assert [(row["version"],row["status"]) for row in selected_rows] == [
                (1,"Superseded"),(2,"Draft")
            ]
            assert selected_rows[0]["content_md"] == "# Handout v1"
            assert selected_rows[1]["content_md"] == "# Handout v2"
            assert preserved_result == preserved_v1
            assert preserved["version"] == 1
            assert preserved["status"] == "Preserved"
            assert preserved["content_md"] == "# Materials v1"
    finally:
        campus.DB_PATH=original


def test_v081_selective_revision_end_to_end_skips_preserved_research():
    import asyncio
    import json
    from ai.provider import GenerationResult

    original_db=campus.DB_PATH
    original_pause=campus.pause
    original_provider=campus.get_role_provider
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Selective E2E","Active",now,now)
                )
                project_id=int(cur.lastrowid)

                task_ids={}
                for seq,title,owner,status in [
                    (1,"Research","research","Completed"),
                    (2,"Programs","programs","Waiting"),
                    (3,"Chief Review","chief","Waiting"),
                ]:
                    cur=conn.execute(
                        """
                        INSERT INTO tasks(
                            project_id,title,owner_agent_id,status,sequence,brief,result,
                            created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            project_id,title,owner,status,seq,title,
                            "PRESERVED RESEARCH RESULT" if owner=="research" else f"Old {title}",
                            now,now
                        )
                    )
                    task_ids[owner]=int(cur.lastrowid)

                expected=[
                    {"type":"research_brief","title":"Research Brief","purpose":"Research"},
                    {"type":"lesson_plan","title":"Lesson Plan","purpose":"Teach"},
                    {"type":"facilitator_guide","title":"Facilitator Guide","purpose":"Guide"},
                    {"type":"materials_list","title":"Materials","purpose":"Prepare"},
                    {"type":"participant_handout","title":"Handout","purpose":"Share"},
                    {"type":"executive_summary","title":"Executive Summary","purpose":"Decide"},
                ]
                conn.execute(
                    """
                    INSERT INTO chief_plans(
                        project_id,summary,success_criteria_json,questions_json,risk_notes_json,
                        expected_deliverables_json,provider,model,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Build a class.",json.dumps(["Useful revised class"]),
                        "[]","[]",json.dumps(expected),"gemini","fake",now
                    )
                )
                conn.execute(
                    """
                    INSERT INTO research_artifacts(
                        task_id,project_id,content_json,provider,model,created_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        task_ids["research"],project_id,
                        json.dumps({
                            "executive_summary":"Preserved research.",
                            "findings":["Finding"],
                            "practical_recommendations":["Recommendation"],
                            "uncertainties":[],
                            "verification_needed":[],
                            "handoff_note":"Use this."
                        }),
                        "gemini","old-research",now
                    )
                )

                existing={}
                for dtype,title,source,creator,provider in [
                    ("research_brief","Research Brief","research","Research","gemini"),
                    ("lesson_plan","Lesson Plan","programs","Programs","openai"),
                    ("facilitator_guide","Facilitator Guide","programs","Programs","openai"),
                    ("materials_list","Materials","programs","Programs","openai"),
                    ("participant_handout","Handout","programs","Programs","openai"),
                    ("executive_summary","Executive Summary","chief","Chief of Staff","gemini"),
                ]:
                    existing[dtype]=campus.upsert_deliverable(
                        conn,project_id=project_id,source_task_id=task_ids[source],
                        deliverable_type=dtype,title=title,purpose=title,
                        content_md=f"# {title} v1",created_by=creator,
                        provider=provider,model="old",status="Preserved"
                    )

                cur=conn.execute(
                    """
                    INSERT INTO revision_requests(
                        project_id,source_approval_id,request_text,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        project_id,None,
                        "Make only the handout simpler for children.",
                        "Executing",now,now
                    )
                )
                request_id=int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO revision_plans(
                        project_id,request_id,revision_number,summary,task_revisions_json,
                        deliverable_revisions_json,preserve_keys_json,questions_json,
                        provider,model,attempt_count,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,request_id,1,"Revise the handout only.",
                        json.dumps([{
                            "task_id":task_ids["programs"],
                            "reason":"Handout revision.",
                            "revision_brief":"Make the participant handout simpler for children."
                        }]),
                        json.dumps([{
                            "deliverable_key":f"participant_handout:task:{task_ids['programs']}",
                            "reason":"Simpler wording."
                        }]),
                        json.dumps([
                            f"research_brief:task:{task_ids['research']}",
                            f"lesson_plan:task:{task_ids['programs']}",
                            f"facilitator_guide:task:{task_ids['programs']}",
                            f"materials_list:task:{task_ids['programs']}",
                        ]),
                        "[]","gemini","fake-chief",1,"Executing",now,now
                    )
                )
                conn.execute(
                    "UPDATE deliverables SET status='Revision Queued' WHERE id IN (?,?)",
                    (existing["participant_handout"],existing["executive_summary"])
                )
                conn.execute(
                    """
                    UPDATE deliverables SET status='Preserved'
                    WHERE project_id=? AND id NOT IN (?,?)
                    """,
                    (
                        project_id,
                        existing["participant_handout"],
                        existing["executive_summary"]
                    )
                )

            class FakeProvider:
                def generate_text(self,prompt,max_output_tokens=120):
                    if "APPROVED PROGRAMS TASK" in prompt:
                        assert "Make the participant handout simpler for children." in prompt
                        text=json.dumps({
                            "deliverable_title":"Lesson Plan",
                            "program_summary":"A revised class.",
                            "audience":"All ages",
                            "duration_minutes":45,
                            "objectives":["Learn"],
                            "run_of_show":[{
                                "minutes":45,"segment":"Class","purpose":"Teach",
                                "facilitator_action":"Teach."
                            }],
                            "materials":["Paper"],
                            "participant_activities":["Practice"],
                            "facilitator_notes":["Keep prior plan."],
                            "handout_or_resource_ideas":["Kid-friendly checklist"],
                            "research_integration":["Preserved research."],
                            "verification_flags":[],
                            "handoff_note":"Handout revised."
                        })
                        return GenerationResult(
                            "openai","fake-programs",text,len(prompt),len(text)
                        )
                    if "FINAL CHIEF TASK:" in prompt:
                        assert "Human revision instruction: Make only the handout simpler for children." in prompt
                        text=json.dumps({
                            "review_title":"Revised Package",
                            "executive_summary":"Only the requested handout changed.",
                            "approval_recommendation":"approve_internal",
                            "success_criteria_review":[{
                                "criterion":"Useful revised class",
                                "status":"met",
                                "evidence":"Revised handout is present."
                            }],
                            "deliverable_review":[],
                            "research_programs_alignment":["Preserved research remains aligned."],
                            "gaps_or_conflicts":[],
                            "verification_before_public_use":[],
                            "recommended_revisions":[],
                            "executive_decisions_needed":["Approve revised package."],
                            "final_package_summary":"Preserved package plus handout v2.",
                            "handoff_note":"Review Outputs."
                        })
                        return GenerationResult(
                            "gemini","fake-chief",text,len(prompt),len(text)
                        )
                    raise AssertionError("Unexpected AI call in selective revision")

            async def no_pause(seconds=0):
                return None
            campus.pause=no_pause
            campus.get_role_provider=lambda role: FakeProvider()

            asyncio.run(
                campus.execute_approved_plan(
                    project_id,
                    revision=True,
                )
            )

            with campus.db() as conn:
                research_task=conn.execute(
                    "SELECT * FROM tasks WHERE id=?",(task_ids["research"],)
                ).fetchone()
                participant=conn.execute(
                    """
                    SELECT version,status,content_md
                    FROM deliverables
                    WHERE project_id=? AND deliverable_type='participant_handout'
                    ORDER BY version
                    """,
                    (project_id,)
                ).fetchall()
                lesson=conn.execute(
                    """
                    SELECT version,status,content_md
                    FROM deliverables
                    WHERE project_id=? AND deliverable_type='lesson_plan'
                    ORDER BY version
                    """,
                    (project_id,)
                ).fetchall()
                executive=conn.execute(
                    """
                    SELECT version,status
                    FROM deliverables
                    WHERE project_id=? AND deliverable_type='executive_summary'
                    ORDER BY version
                    """,
                    (project_id,)
                ).fetchall()
                calls=conn.execute(
                    """
                    SELECT operation FROM ai_calls
                    WHERE project_id=? AND status='Success'
                    ORDER BY id
                    """,
                    (project_id,)
                ).fetchall()
                project=conn.execute(
                    "SELECT status FROM projects WHERE id=?",(project_id,)
                ).fetchone()
                revision_plan=conn.execute(
                    "SELECT status FROM revision_plans WHERE project_id=?",
                    (project_id,)
                ).fetchone()

            assert research_task["status"] == "Completed"
            assert research_task["result"] == "PRESERVED RESEARCH RESULT"
            assert len(participant) == 2
            assert participant[0]["version"] == 1
            assert participant[0]["status"] == "Superseded"
            assert participant[1]["version"] == 2
            assert len(lesson) == 1
            assert lesson[0]["version"] == 1
            assert "# Lesson Plan v1" in lesson[0]["content_md"]
            assert len(executive) == 2
            assert executive[0]["status"] == "Superseded"
            assert executive[1]["version"] == 2
            assert [row["operation"] for row in calls] == [
                "programs_task","chief_final_review"
            ]
            assert project["status"] == "Awaiting Execution Review"
            assert revision_plan["status"] == "Awaiting Human Review"
    finally:
        campus.pause=original_pause
        campus.get_role_provider=original_provider
        campus.DB_PATH=original_db


def test_v081_changing_revision_plan_does_not_start_work():
    import asyncio
    import json

    original_db=campus.DB_PATH
    original_workflow=campus.workflow_task
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            campus.workflow_task=None
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Change Plan Test","Awaiting Revision Approval",now,now)
                )
                project_id=int(cur.lastrowid)
                cur=conn.execute(
                    """
                    INSERT INTO revision_requests(
                        project_id,source_approval_id,request_text,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        project_id,None,"Revise handout.","Awaiting Approval",now,now
                    )
                )
                request_id=int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO revision_plans(
                        project_id,request_id,revision_number,summary,task_revisions_json,
                        deliverable_revisions_json,preserve_keys_json,questions_json,
                        provider,model,attempt_count,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,request_id,1,"Plan one.","[]","[]","[]","[]",
                        "gemini","fake",1,"Awaiting Approval",now,now
                    )
                )
                cur=conn.execute(
                    """
                    INSERT INTO approvals(
                        project_id,title,summary,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        project_id,"Approve revision plan: Change Plan Test — Revision 1",
                        "Plan.","Pending",now,now
                    )
                )
                approval_id=int(cur.lastrowid)

            result=asyncio.run(
                campus.api_approval_decide(
                    approval_id,
                    campus.ApprovalDecision(
                        decision="changes",
                        note="Also keep the lesson plan unchanged."
                    )
                )
            )

            with campus.db() as conn:
                project=conn.execute(
                    "SELECT status FROM projects WHERE id=?",(project_id,)
                ).fetchone()
                plan=conn.execute(
                    "SELECT status FROM revision_plans WHERE project_id=?",(project_id,)
                ).fetchone()
                request=conn.execute(
                    "SELECT * FROM revision_requests WHERE id=?",(request_id,)
                ).fetchone()

            assert result["revision_execution_started"] is False
            assert project["status"] == "Needs Revision"
            assert plan["status"] == "Changes Requested"
            assert request["status"] == "Requested"
            assert "keep the lesson plan unchanged" in request["request_text"]
            assert campus.workflow_task is None
    finally:
        campus.workflow_task=original_workflow
        campus.DB_PATH=original_db


def test_v081_revision_gate_repair_and_restart_preservation():
    original=campus.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.init_db()
            now=campus.utc_now()

            with campus.db() as conn:
                cur=conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Repair Revision Gate","Awaiting Revision Approval",now,now)
                )
                project_id=int(cur.lastrowid)
                cur=conn.execute(
                    """
                    INSERT INTO revision_requests(
                        project_id,source_approval_id,request_text,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        project_id,None,"Revise.","Awaiting Approval",now,now
                    )
                )
                request_id=int(cur.lastrowid)
                conn.execute(
                    """
                    INSERT INTO revision_plans(
                        project_id,request_id,revision_number,summary,task_revisions_json,
                        deliverable_revisions_json,preserve_keys_json,questions_json,
                        provider,model,attempt_count,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        project_id,request_id,1,"Selective plan.","[]","[]","[]","[]",
                        "gemini","fake",1,"Awaiting Approval",now,now
                    )
                )
                campus.set_workflow_run(
                    conn,project_id,state="Awaiting Revision Approval",
                    current_task_id=None,last_error=None
                )

            recovered=campus.reconcile_interrupted_workflows()
            assert recovered == []
            repaired=campus.repair_approval_invariants()
            assert repaired["repaired"] == 1

            with campus.db() as conn:
                project=conn.execute(
                    "SELECT status FROM projects WHERE id=?",(project_id,)
                ).fetchone()
                approval=conn.execute(
                    """
                    SELECT * FROM approvals
                    WHERE project_id=? AND status='Pending'
                      AND title LIKE 'Approve revision plan:%'
                    """,
                    (project_id,)
                ).fetchone()

            assert project["status"] == "Awaiting Revision Approval"
            assert approval is not None
    finally:
        campus.DB_PATH=original


def test_v081_revision_ui_and_manifest():
    import json

    index=(ROOT/"static/index.html").read_text(encoding="utf-8")
    js=(ROOT/"static/js/app.js").read_text(encoding="utf-8")
    css=(ROOT/"static/css/world.css").read_text(encoding="utf-8")
    app_text=(ROOT/"app.py").read_text(encoding="utf-8")
    prompt=(ROOT/"prompts/chief_revision.txt").read_text(encoding="utf-8")

    assert LIVE_SHELL_LABEL in index
    assert 'id="rail-revision-plan-count"' in index
    assert "Ask Stella to Plan Revision" in js
    assert "Approve selective revision" in js
    assert "Previous Versions" in js
    assert "Superseded versions remain readable" in js
    assert "function planRevision(projectId)" in js
    assert "chief_revision_plan:'Stella revision planning'" in js

    assert ".revision-plan-button" in css
    assert ".revision-plan-card" in css
    assert ".deliverable-card.status-revision-queued" in css

    assert '@app.post("/api/projects/{project_id}/revision/plan")' in app_text
    assert "revision_requests" in app_text
    assert "revision_plans" in app_text
    assert "Revision Queued" in app_text
    assert "Preserved" in app_text

    assert "REVISION PLANNING ONLY" in prompt
    assert "Select only existing task IDs" in prompt
    assert "Select only supplied deliverable keys" in prompt

    data=json.loads(
        (ROOT/"static/assets/asset-manifest.json").read_text(encoding="utf-8")
    )
    assert data["build"] == LIVE_BUILD
    assert data["ai_runtime"]["stabilization_recovery"]["schema_version"] == LIVE_VERSION
    revision=data["ai_runtime"]["revision_loop"]
    assert revision["enabled"] is True
    assert revision["planner"] == "chief-real-ai-routed"
    assert revision["human_revision_plan_approval"] is True
    assert revision["preserve_unselected_tasks"] is True
    assert revision["preserve_unselected_outputs"] is True
    assert revision["new_version_only_for_revision_queued_outputs"] is True
    assert revision["previous_versions_readable"] is True
    assert revision["automatic_revision_execution"] is False
    assert revision["automatic_provider_fallback"] is False


def test_v0811_repository_schema_and_health():
    original=campus.DB_PATH
    original_repo=campus.REPOSITORY
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.REPOSITORY=Path(td)/"repository"
            campus.init_db()
            with campus.db() as conn:
                tables={row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                cols={row[1] for row in conn.execute("PRAGMA table_info(project_files)")}
                health=campus.system_health(conn)
            assert "project_files" in tables
            assert {"project_id","source_deliverable_id","display_name","filename","relative_path","file_kind","version","status"}.issubset(cols)
            assert health["ok"] is True
            assert health["schema_version"] == LIVE_VERSION
    finally:
        campus.DB_PATH=original
        campus.REPOSITORY=original_repo


def test_v0811_deliverable_auto_files_markdown_without_ai_call():
    original=campus.DB_PATH
    original_repo=campus.REPOSITORY
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.REPOSITORY=Path(td)/"repository"
            campus.init_db()
            now=campus.utc_now()
            with campus.db() as conn:
                project_id=int(conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Repository Test","Active",now,now)
                ).lastrowid)
                before=conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]
                deliverable_id=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=None,
                    deliverable_type="project_output",title="Final Paperwork",purpose="File it",
                    content_md="# Final Paperwork\n\nUseful content.",created_by="Programs",
                    provider="openai",model="fake",status="Approval Ready"
                )
                after=conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]
                file=conn.execute("SELECT * FROM project_files WHERE source_deliverable_id=?",(deliverable_id,)).fetchone()
            assert before == after == 0
            assert file is not None
            assert file["file_kind"] == "text"
            assert file["status"] == "Current"
            path=campus._repository_safe_path(file["relative_path"])
            assert path.is_file()
            assert "Useful content." in path.read_text(encoding="utf-8")
    finally:
        campus.DB_PATH=original
        campus.REPOSITORY=original_repo


def test_v0811_repository_tracks_output_versions():
    import json
    original=campus.DB_PATH
    original_repo=campus.REPOSITORY
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.REPOSITORY=Path(td)/"repository"
            campus.init_db()
            now=campus.utc_now()
            with campus.db() as conn:
                project_id=int(conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Version Files","Active",now,now)
                ).lastrowid)
                task_id=int(conn.execute(
                    "INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (project_id,"Programs","programs","Waiting",1,"Revise",now,now)
                ).lastrowid)
                v1=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=task_id,
                    deliverable_type="participant_handout",title="Handout",purpose="Handout",
                    content_md="# v1",created_by="Programs",provider="openai",model="fake",status="Revision Review"
                )
                request_id=int(conn.execute(
                    "INSERT INTO revision_requests(project_id,source_approval_id,request_text,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (project_id,None,"Revise","Executing",now,now)
                ).lastrowid)
                conn.execute(
                    "INSERT INTO revision_plans(project_id,request_id,revision_number,summary,task_revisions_json,deliverable_revisions_json,preserve_keys_json,questions_json,provider,model,attempt_count,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (project_id,request_id,1,"Revise",json.dumps([]),json.dumps([]),json.dumps([]),json.dumps([]),"gemini","fake",1,"Executing",now,now)
                )
                conn.execute("UPDATE deliverables SET status='Revision Queued' WHERE id=?",(v1,))
                v2=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=task_id,
                    deliverable_type="participant_handout",title="Handout",purpose="Handout",
                    content_md="# v2",created_by="Programs",provider="openai",model="fake",status="Draft"
                )
                files=conn.execute("SELECT version,status,relative_path FROM project_files WHERE project_id=? ORDER BY version",(project_id,)).fetchall()
            assert v2 != v1
            assert [(r["version"],r["status"]) for r in files] == [(1,"Previous"),(2,"Current")]
            assert campus._repository_safe_path(files[0]["relative_path"]).read_text(encoding="utf-8") == "# v1"
            assert campus._repository_safe_path(files[1]["relative_path"]).read_text(encoding="utf-8") == "# v2"
    finally:
        campus.DB_PATH=original
        campus.REPOSITORY=original_repo


def test_v0811_repository_rescan_registers_future_artifact_types():
    original=campus.DB_PATH
    original_repo=campus.REPOSITORY
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.REPOSITORY=Path(td)/"repository"
            campus.init_db()
            now=campus.utc_now()
            with campus.db() as conn:
                project_id=int(conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Slides Project","Completed",now,now)
                ).lastrowid)
                folder=campus._repository_project_dir(conn,project_id)
                deck=folder/"final-class-slides.pptx"
                deck.write_bytes(b"placeholder-pptx-file-for-registry-test")
                count=campus.rescan_repository(conn)
                row=conn.execute("SELECT * FROM project_files WHERE project_id=? AND filename=?",(project_id,deck.name)).fetchone()
            assert count == 1
            assert row["file_kind"] == "slides"
            assert row["status"] == "Current"
    finally:
        campus.DB_PATH=original
        campus.REPOSITORY=original_repo


def test_v0811_repository_state_and_download_routes():
    import asyncio
    original=campus.DB_PATH
    original_repo=campus.REPOSITORY
    try:
        with tempfile.TemporaryDirectory() as td:
            campus.DB_PATH=Path(td)/"test.db"
            campus.REPOSITORY=Path(td)/"repository"
            campus.init_db()
            now=campus.utc_now()
            with campus.db() as conn:
                project_id=int(conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    ("Route Project","Completed",now,now)
                ).lastrowid)
                deliverable_id=campus.upsert_deliverable(
                    conn,project_id=project_id,source_task_id=None,deliverable_type="project_output",
                    title="Repository Route",purpose="Route",content_md="# Route",created_by="Chief of Staff",
                    provider="gemini",model="fake",status="Approved"
                )
                file_id=int(conn.execute("SELECT id FROM project_files WHERE source_deliverable_id=?",(deliverable_id,)).fetchone()[0])
            state=campus.current_state()
            item=next(f for f in state["project_files"] if int(f["id"])==file_id)
            assert item["project_title"] == "Route Project"
            assert item["exists"] is True
            download=asyncio.run(campus.api_repository_file_download(file_id))
            view=asyncio.run(campus.api_repository_file_view(file_id))
            assert Path(download.path).is_file()
            assert Path(view.path).is_file()
    finally:
        campus.DB_PATH=original
        campus.REPOSITORY=original_repo


def test_v0811_repository_and_readability_ui():
    index=(ROOT/"static/index.html").read_text(encoding="utf-8")
    js=(ROOT/"static/js/app.js").read_text(encoding="utf-8")
    css=(ROOT/"static/css/app.css").read_text(encoding="utf-8")
    assert LIVE_SHELL_LABEL in index
    assert 'id="repository-btn"' in index
    assert 'id="top-repository-count"' in index
    assert 'data-panel="repository"' in index
    assert 'id="focus-workspace-btn"' in index
    assert 'id="overview-repository"' in index
    assert "Project Repository" in js
    assert "function drawerRepository()" in js
    assert "function setFocusWorkspace(enabled)" in js
    assert "Previous Files" in js
    assert "['files'" in js or "['files'," in js
    assert ".dashboard-rail{position:static!important" in css
    assert ".focus-workspace .left-rail" in css
    assert ".repository-file-card" in css
    assert ".task-result" in css
    assert ".activity-item" in css


def test_v0811_manifest_repository_and_workspace():
    import json
    data=json.loads((ROOT/"static/assets/asset-manifest.json").read_text(encoding="utf-8"))
    assert data["build"] == LIVE_BUILD
    assert data["ai_runtime"]["stabilization_recovery"]["schema_version"] == LIVE_VERSION
    repo=data["project_repository"]
    assert repo["enabled"] is True
    assert repo["table"] == "project_files"
    assert repo["auto_file_deliverables_as_markdown"] is True
    assert repo["manual_rescan"] is True
    assert repo["additional_ai_calls"] is False
    workspace=data["workspace_readability"]
    assert workspace["side_rails_sticky"] is False
    assert workspace["prevents_lower_panel_overlap"] is True
    assert workspace["focus_workspace_toggle"] is True


def test_v082_institutional_memory_schema_context_and_reset_survival(tmp_path):
    import app as campus
    original = campus.DB_PATH
    campus.DB_PATH = tmp_path / "mavis.db"
    try:
        campus.init_db()
        with campus.db() as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert "institutional_memory" in tables
            assert campus.system_health(conn)["schema_version"] == LIVE_VERSION
            now = campus.utc_now()
            project_id = int(conn.execute(
                "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                ("Memory Test", "Active", now, now),
            ).lastrowid)
            conn.execute(
                """
                INSERT INTO institutional_memory(
                    project_id,memory_type,title,body,tags,importance,source_kind,status,created_by,created_at,updated_at
                ) VALUES(NULL,'Policy','Institution policy','Keep human approval gates.','approval','Core','manual','Active','Human',?,?)
                """,
                (now, now),
            )
            conn.execute(
                """
                INSERT INTO institutional_memory(
                    project_id,memory_type,title,body,tags,importance,source_kind,status,created_by,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (project_id,'Decision','Project decision','Use the approved project method.','project','Normal','manual','Active','Human',now,now),
            )
            conn.execute(
                """
                INSERT INTO institutional_memory(
                    project_id,memory_type,title,body,tags,importance,source_kind,status,created_by,created_at,updated_at
                ) VALUES(NULL,'Context','Archived item','Do not send this to AI.','','Core','manual','Archived','Human',?,?)
                """,
                (now, now),
            )
            context = campus.institutional_memory_for_prompt(conn, project_id)
            assert [item["title"] for item in context] == ["Institution policy", "Project decision"]
            assert all(item["title"] != "Archived item" for item in context)

        campus.reset_runtime()
        with campus.db() as conn:
            memories = conn.execute("SELECT title,project_id,status FROM institutional_memory ORDER BY id").fetchall()
            assert len(memories) == 3
            assert all(row["project_id"] is None for row in memories)
            statuses = {row["title"]: row["status"] for row in memories}
            assert statuses["Institution policy"] == "Active"
            assert statuses["Project decision"] == "Archived"
            assert statuses["Archived item"] == "Archived"
            assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
    finally:
        campus.DB_PATH = original


def test_v082_memory_ui_and_no_calendar_scope():
    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/app.css").read_text(encoding="utf-8")
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert LIVE_SHELL_LABEL in index
    assert 'id="memory-btn"' in index
    assert 'data-panel="memory"' in index
    assert "drawerMemory" in js
    assert "data-memory-form" in js
    assert "data-memory-status" in js
    assert "projectMemories" in js
    assert ".memory-card" in css
    assert 'CREATE TABLE IF NOT EXISTS institutional_memory' in app_text
    assert '@app.post("/api/memory")' in app_text
    assert '@app.post("/api/memory/{memory_id}/status")' in app_text
    assert "Google Calendar v1" in readme
    assert '"calendar_integration_enabled": False' in app_text


def test_v082_chief_receives_bounded_human_curated_memory():
    from agents.chief_of_staff import plan_project
    from ai.provider import GenerationResult

    class Provider:
        def __init__(self):
            self.prompt = ""
        def generate_text(self, prompt, *, max_output_tokens):
            self.prompt = prompt
            return GenerationResult(
                text='''{"project_title":"Memory Plan","summary":"Use memory safely.","success_criteria":["Done"],"tasks":[{"title":"Research","owner":"research","brief":"Research it"},{"title":"Review","owner":"chief","brief":"Review it"}],"questions_for_executive":[],"risk_notes":[]}''',
                provider="fake",
                model="fake",
                input_chars=len(prompt),
                output_chars=300,
            )

    provider = Provider()
    result = plan_project(provider, "Plan a project.", [{
        "id": 1,
        "scope": "Institution-wide",
        "memory_type": "Policy",
        "title": "Human approval",
        "body": "Keep a human approval gate.",
        "tags": "approval",
        "importance": "Core",
        "source": "manual",
        "created_by": "Human",
    }])
    assert result.plan["project_title"] == "Memory Plan"
    assert "HUMAN-CURATED INSTITUTIONAL MEMORY" in provider.prompt
    assert "Human approval" in provider.prompt
    assert "current executive request wins" in provider.prompt


def test_v083_memory_capture_edit_and_provenance(tmp_path):
    import app as campus
    old_db = campus.DB_PATH
    old_repo = campus.REPOSITORY
    campus.DB_PATH = tmp_path / "mavis.db"
    campus.REPOSITORY = tmp_path / "repository"
    try:
        campus.init_db()
        with campus.db() as conn:
            now = campus.utc_now()
            project_id = conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)", ("Capture Test","Active",now,now)).lastrowid
            note_id = conn.execute("INSERT INTO notes(project_id,task_id,author,body,created_at) VALUES(?,?,?,?,?)", (project_id,None,"Human","Remember this durable project lesson.",now)).lastrowid
            deliverable_id = conn.execute("INSERT INTO deliverables(project_id,source_task_id,deliverable_key,deliverable_type,title,purpose,status,content_md,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (project_id,None,"decision_memo:chief","decision_memo","Decision Memo","Decision","Ready","# Keep this\n\nDurable output.",1,"Chief of Staff",now,now)).lastrowid
        source = None
        with campus.db() as conn:
            source = campus._memory_capture_source(conn,"note",note_id)
            assert source["project_id"] == project_id
            assert source["source_kind"] == "note"
            assert "durable project lesson" in source["body"]
            dsource = campus._memory_capture_source(conn,"deliverable",deliverable_id)
            assert dsource["source_kind"] == "deliverable"
            assert "Durable output" in dsource["body"]
        assert campus.SCHEMA_VERSION == LIVE_VERSION
    finally:
        campus.DB_PATH = old_db
        campus.REPOSITORY = old_repo


def test_v083_memory_capture_and_edit_routes_are_wired():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    app_py = (root / "app.py").read_text(encoding="utf-8")
    js = (root / "static/js/app.js").read_text(encoding="utf-8")
    html = (root / "static/index.html").read_text(encoding="utf-8")
    assert '@app.post("/api/memory/capture")' in app_py
    assert '@app.post("/api/memory/{memory_id}")' in app_py
    assert 'data-memory-capture-kind="note"' in js
    assert 'data-memory-edit=' in js
    assert 'id="deliverable-remember"' in html
    assert '"calendar_integration_enabled": False' in app_py


def test_v084_memory_governance_schema_and_review_math(tmp_path):
    import app as campus
    old_db, old_repo = campus.DB_PATH, campus.REPOSITORY
    campus.DB_PATH = tmp_path / "mavis.db"
    campus.REPOSITORY = tmp_path / "repository"
    try:
        campus.init_db()
        with campus.db() as conn:
            cols={row[1] for row in conn.execute("PRAGMA table_info(institutional_memory)")}
            assert {"reviewed_at","review_interval_days","review_due_at","supersedes_id","superseded_by_id"}.issubset(cols)
            assert campus.system_health(conn)["schema_version"] == LIVE_VERSION
        due=campus.memory_review_due("2026-01-01T00:00:00+00:00",90)
        assert due.startswith("2026-04-01")
        assert campus.memory_review_due("2026-01-01T00:00:00+00:00",0) is None
        assert campus.normalize_review_interval(999)==180
    finally:
        campus.DB_PATH, campus.REPOSITORY = old_db, old_repo


def test_v084_memory_governance_ui_and_routes():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    app_py=(root/"app.py").read_text(encoding="utf-8")
    js=(root/"static/js/app.js").read_text(encoding="utf-8")
    assert '@app.post("/api/memory/{memory_id}/review")' in app_py
    assert '@app.post("/api/memory/{memory_id}/supersede")' in app_py
    assert 'data-memory-review-filter' in js
    assert 'data-memory-supersede' in js
    assert 'review_interval_days' in js
    assert '"calendar_integration_enabled": False' in app_py


def test_v085_playbook_schema_prompt_filter_and_reset(tmp_path):
    import app as campus
    original_db=campus.DB_PATH
    original_repo=campus.REPOSITORY
    try:
        campus.DB_PATH=tmp_path/'mavis.db'
        campus.REPOSITORY=tmp_path/'repository'
        campus.init_db()
        with campus.db() as conn:
            now=campus.utc_now()
            cur=conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",('PB project','Active',now,now))
            pid=int(cur.lastrowid)
            conn.execute("INSERT INTO playbooks(project_id,title,purpose,owner_agent_id,trigger_text,steps_json,tags,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(None,'Institution SOP','Repeat institution work','chief','When starting','[\"Check scope\",\"Ask human\"]','ops','Active','Human',now,now))
            conn.execute("INSERT INTO playbooks(project_id,title,purpose,owner_agent_id,trigger_text,steps_json,tags,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(pid,'Project SOP','Project-only work','chief','When revising','[\"Preserve output\"]','project','Active','Human',now,now))
            conn.execute("INSERT INTO playbooks(project_id,title,purpose,owner_agent_id,trigger_text,steps_json,tags,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(None,'Draft SOP','Not ready',None,'','[\"Nope\"]','','Draft','Human',now,now))
            initial=campus.playbooks_for_prompt(conn)
            scoped=campus.playbooks_for_prompt(conn,pid)
            assert [x['title'] for x in initial]==['Institution SOP']
            assert {x['title'] for x in scoped}=={'Institution SOP','Project SOP'}
        campus.reset_runtime()
        with campus.db() as conn:
            pbs=conn.execute("SELECT title,project_id,status FROM playbooks ORDER BY id").fetchall()
            assert pbs[0]['status']=='Active' and pbs[0]['project_id'] is None
            assert pbs[1]['status']=='Archived' and pbs[1]['project_id'] is None
    finally:
        campus.DB_PATH=original_db
        campus.REPOSITORY=original_repo


def test_v085_playbook_ui_manifest_and_no_calendar():
    import json
    index=(ROOT/'static/index.html').read_text(encoding='utf-8')
    js=(ROOT/'static/js/app.js').read_text(encoding='utf-8')
    readme=(ROOT/'README.md').read_text(encoding='utf-8')
    data=json.loads((ROOT/'static/assets/asset-manifest.json').read_text(encoding='utf-8'))
    assert LIVE_SHELL_LABEL in index
    assert 'data-panel="playbooks"' in index
    assert 'drawerPlaybooks' in js and 'data-playbook-form' in js
    assert data['institutional_playbooks']['enabled'] is True
    assert data['institutional_playbooks']['external_action_authority'] is False
    assert data['institutional_playbooks']['google_calendar_integration'] is False
    assert 'Google Calendar v1' in readme


def test_v086_executive_briefing_is_local_and_snapshots_survive_reset(tmp_path):
    import json
    import app as campus
    original_db=campus.DB_PATH
    original_repo=campus.REPOSITORY
    try:
        campus.DB_PATH=tmp_path/'mavis.db'
        campus.REPOSITORY=tmp_path/'repository'
        campus.init_db()
        with campus.db() as conn:
            now=campus.utc_now()
            cur=conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",('Brief project','Active',now,now))
            pid=int(cur.lastrowid)
            conn.execute("INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(pid,'Done task','chief','Completed',1,'done',now,now))
            conn.execute("INSERT INTO playbooks(project_id,title,purpose,owner_agent_id,trigger_text,steps_json,tags,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(None,'Brief SOP','Use procedure','chief','When needed','[\"Check\"]','','Active','Human',now,now))
            conn.execute("INSERT INTO institutional_memory(project_id,memory_type,title,body,tags,importance,source_kind,status,created_by,created_at,updated_at,reviewed_at,review_interval_days,review_due_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(None,'Policy','Review me','Old policy','','Core','manual','Active','Human',now,now,now,90,'2000-01-01T00:00:00+00:00'))
            before_calls=conn.execute('SELECT COUNT(*) FROM ai_calls').fetchone()[0]
            brief=campus.executive_briefing(conn)
            after_calls=conn.execute('SELECT COUNT(*) FROM ai_calls').fetchone()[0]
            assert before_calls==after_calls==0
            assert brief['additional_ai_calls']==0
            assert brief['counts']['memory_review_due']==1
            assert brief['counts']['active_playbooks']==1
            conn.execute("INSERT INTO briefing_snapshots(captured_at,brief_json,created_by) VALUES(?,?,?)",(now,json.dumps(brief),'Human'))
        campus.reset_runtime()
        with campus.db() as conn:
            assert conn.execute('SELECT COUNT(*) FROM briefing_snapshots').fetchone()[0]==1
    finally:
        campus.DB_PATH=original_db
        campus.REPOSITORY=original_repo


def test_v086_briefing_ui_manifest_and_no_scheduled_integrations():
    import json
    index=(ROOT/'static/index.html').read_text(encoding='utf-8')
    js=(ROOT/'static/js/app.js').read_text(encoding='utf-8')
    readme=(ROOT/'README.md').read_text(encoding='utf-8')
    data=json.loads((ROOT/'static/assets/asset-manifest.json').read_text(encoding='utf-8'))
    assert LIVE_SHELL_LABEL in index
    assert 'data-panel="briefing"' in index and 'drawerBriefing' in js
    assert '/api/briefing/snapshot' in js
    brief=data['executive_briefing']
    assert brief['additional_ai_calls']==0
    assert brief['automatic_calendar'] is False and brief['automatic_email'] is False
    assert brief['google_calendar_integration'] is True
    assert 'Google Calendar v1' in readme


def test_v0861_library_foundation_schema_is_local_durable_and_empty(tmp_path):
    import app as campus
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.init_db()
        with campus.db() as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert {"library_collections", "library_materials"}.issubset(tables)
            assert campus.system_health(conn)["ok"] is True
            assert campus.system_health(conn)["schema_version"] == LIVE_VERSION
            summary = campus.library_foundation_summary(conn)
            assert summary == {
                "enabled": True,
                "phase": "programs_auto_archive",
                "cataloging_desk_enabled": True,
                "trusted_material_file_access_enabled": True,
                "collections": 0,
                "active_collections": 0,
                "materials": 0,
                "incoming_materials": 0,
                "indexed_materials": 0,
                "needs_ocr_materials": 0,
                "local_only": True,
                "additional_ai_calls": 0,
                "catalog_enabled": True,
                "catalog_search_enabled": True,
                "uploads_enabled": True,
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
                "program_auto_archive_events": 0,
            }
            before_ai = conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]
            now = campus.utc_now()
            cid = conn.execute(
                "INSERT INTO library_collections(title,collection_type,subject,description,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                ("Tinctures 101", "Program", "Herbal Skills", "Historical class collection", "Active", "Human", now, now),
            ).lastrowid
            conn.execute(
                "INSERT INTO library_materials(collection_id,title,material_type,edition_label,edition_date,status,source_kind,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (cid, "Tinctures 101 Slideshow", "Presentation", "2026", "2026-08-01", "Cataloged", "manual", "Foundation test record", "Human", now, now),
            )
            after_ai = conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]
            assert before_ai == after_ai == 0
        campus.reset_runtime()
        with campus.db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM library_collections").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM library_materials").fetchone()[0] == 1
            assert campus.library_foundation_summary(conn)["materials"] == 1
    finally:
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v0861_manifest_and_roadmap_keep_future_integrations_deferred():
    import json
    data = json.loads((ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    lib = data["library_foundation"]
    assert data["build"] == LIVE_BUILD
    assert data["version"] == LIVE_VERSION
    assert lib["tables"] == ["library_collections", "library_materials", "library_material_index", "library_inbox", "programs_library_preflights", "program_archive_events"]
    assert lib["local_only"] is True and lib["additional_ai_calls"] == 0
    assert lib["uploads_enabled"] is True
    assert lib["librarian_agent_enabled"] is True
    future = data["future_planning_context"]
    assert future["calendar"] == "internal_calendar_with_manual_read_only_google_primary_sync"
    assert future["local_weather"] == "live_pws_with_open_meteo_fallback"
    assert future["seasonal_awareness"] == "local_enabled"
    assert future["automatic_rescheduling"] is False
    assert "Weather & Seasons" in readme
    assert "Google Calendar v1" in readme


def test_v0865_library_catalog_crud_search_and_reset(tmp_path):
    import asyncio
    import app as campus
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.init_db()
        with campus.db() as conn:
            assert campus.library_foundation_summary(conn)["phase"] == "programs_auto_archive"
            assert campus.library_foundation_summary(conn)["catalog_search_enabled"] is True
            before_ai = conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]

        first = asyncio.run(campus.api_library_collection_create(campus.LibraryCollectionRequest(
            title="Tinctures 101",
            collection_type="Class",
            subject="Herbalism",
            description="A hands-on Mavis Institute tincture class.",
            status="Active",
        )))
        second = asyncio.run(campus.api_library_collection_create(campus.LibraryCollectionRequest(
            title="Digital Hygiene",
            collection_type="Program",
            subject="Technology",
            description="Practical digital organization and safety.",
            status="Active",
        )))
        assert first["additional_ai_calls"] == second["additional_ai_calls"] == 0

        found = asyncio.run(campus.api_library_catalog(q="tincture", collection_type="all", status="Active", limit=100))
        assert found["local_only"] is True and found["additional_ai_calls"] == 0
        assert found["count"] == 1
        assert found["collections"][0]["title"] == "Tinctures 101"

        edit = asyncio.run(campus.api_library_collection_edit(first["collection_id"], campus.LibraryCollectionRequest(
            title="Tinctures 101 — 2026",
            collection_type="Class",
            subject="Herbalism",
            description="Current catalog record for the 2026 tincture class.",
            status="Active",
        )))
        assert edit["status"] == "updated"
        asyncio.run(campus.api_library_collection_status(first["collection_id"], campus.LibraryCollectionStatusRequest(status="Archived")))

        state = campus.current_state()
        record = next(x for x in state["library_collections"] if x["id"] == first["collection_id"])
        assert record["title"] == "Tinctures 101 — 2026"
        assert record["status"] == "Archived"
        assert state["library_foundation"]["collections"] == 2

        campus.reset_runtime()
        with campus.db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM library_collections").fetchone()[0] == 2
            after_ai = conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]
            assert before_ai == after_ai == 0
    finally:
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v0865_library_catalog_validation_is_bounded():
    import app as campus
    from fastapi import HTTPException
    try:
        campus._clean_library_collection_request(campus.LibraryCollectionRequest(title="", collection_type="Class"))
        raise AssertionError("blank title should fail")
    except HTTPException as exc:
        assert exc.status_code == 400
    try:
        campus._clean_library_collection_request(campus.LibraryCollectionRequest(title="Test", collection_type="Web Portal"))
        raise AssertionError("unknown type should fail")
    except HTTPException as exc:
        assert exc.status_code == 400


def test_v0865_library_catalog_ui_manifest_and_cache_key():
    import json
    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    data = json.loads((ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8"))
    assert LIVE_SHELL_LABEL in index
    assert 'data-panel="library"' in index
    assert f'app.js?v={LIVE_CACHE_KEY}' in index
    assert f'app.css?v={LIVE_CACHE_KEY}' in index
    assert 'drawerLibrary' in js
    assert 'data-library-form' in js
    assert 'data-library-search' in js
    assert '/api/library/collections' in js
    assert data["build"] == LIVE_BUILD
    assert data["library_foundation"]["phase"] == "programs_auto_archive"
    assert data["library_foundation"]["catalog_enabled"] is True
    assert data["library_foundation"]["catalog_search_enabled"] is True
    assert data["library_foundation"]["uploads_enabled"] is True
    assert data["library_foundation"]["librarian_agent_enabled"] is True
    assert "zero AI calls" in readme
    assert "no direct web access" in readme
    assert "live weather access" in readme


def _v0865_request(body: bytes, content_type: str = "application/octet-stream", content_length: int | None = None):
    from starlette.requests import Request
    sent = False
    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}
    headers = [(b"content-type", content_type.encode("latin-1"))]
    headers.append((b"content-length", str(len(body) if content_length is None else content_length).encode("ascii")))
    scope = {"type":"http","http_version":"1.1","method":"POST","scheme":"http","path":"/api/library/inbox/upload","raw_path":b"/api/library/inbox/upload","query_string":b"","headers":headers,"client":("test",1234),"server":("test",80)}
    return Request(scope, receive)


def test_v0865_library_intake_upload_dedupe_quarantine_and_reset(tmp_path):
    import asyncio
    import app as campus
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.init_db()
        payload = b"Mavis Institute past class material\nSlide 1\nSlide 2\n"
        result = asyncio.run(campus.api_library_inbox_upload(
            _v0865_request(payload, "application/pdf"), filename="../../Tinctures 2024.pdf"
        ))
        assert result["status"] == "received"
        assert result["quarantined"] is True and result["cataloged"] is False
        assert result["additional_ai_calls"] == 0
        inbox_id = result["inbox_id"]

        with campus.db() as conn:
            row = conn.execute("SELECT * FROM library_inbox WHERE id=?", (inbox_id,)).fetchone()
            assert row["original_filename"] == "Tinctures 2024.pdf"
            assert row["status"] == "Incoming"
            assert row["size_bytes"] == len(payload)
            assert len(row["sha256"]) == 64
            assert conn.execute("SELECT COUNT(*) FROM library_materials").fetchone()[0] == 0
            assert campus.library_foundation_summary(conn)["incoming_materials"] == 1
            file_path = campus.library_inbox_root() / row["stored_filename"]
            assert file_path.read_bytes() == payload

        duplicate = asyncio.run(campus.api_library_inbox_upload(
            _v0865_request(payload, "application/pdf"), filename="Same bytes, another name.pdf"
        ))
        assert duplicate["status"] == "duplicate"
        assert duplicate["inbox_id"] == inbox_id
        with campus.db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM library_inbox").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0] == 0

        catalog = asyncio.run(campus.api_library_catalog(q="Tinctures 2024", collection_type="all", status="all", limit=100))
        assert catalog["count"] == 0
        assert catalog["additional_ai_calls"] == 0

        listed = asyncio.run(campus.api_library_inbox(limit=100))
        assert listed["quarantined"] is True and listed["count"] == 1
        assert listed["items"][0]["id"] == inbox_id

        campus.reset_runtime()
        with campus.db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM library_inbox").fetchone()[0] == 1
            row = conn.execute("SELECT stored_filename FROM library_inbox WHERE id=?", (inbox_id,)).fetchone()
            assert (campus.library_inbox_root() / row["stored_filename"]).exists()
    finally:
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v0865_library_intake_size_guardrail(tmp_path):
    import asyncio
    import app as campus
    from fastapi import HTTPException
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.init_db()
        request = _v0865_request(b"small", content_length=campus.MAX_LIBRARY_UPLOAD_BYTES + 1)
        try:
            asyncio.run(campus.api_library_inbox_upload(request, filename="too-large.zip"))
            raise AssertionError("oversized upload should fail")
        except HTTPException as exc:
            assert exc.status_code == 413
        with campus.db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM library_inbox").fetchone()[0] == 0
    finally:
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v0865_library_intake_ui_manifest_and_quarantine_contract():
    import json
    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    data = json.loads((ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8"))
    assert LIVE_SHELL_LABEL in index
    assert f"app.js?v={LIVE_CACHE_KEY}" in index and f"app.css?v={LIVE_CACHE_KEY}" in index
    assert "data-library-upload-form" in js
    assert "/api/library/inbox/upload" in js
    assert "Incoming files are quarantined" in js
    lib = data["library_foundation"]
    assert lib["phase"] == "programs_auto_archive"
    assert lib["tables"] == ["library_collections", "library_materials", "library_material_index", "library_inbox", "programs_library_preflights", "program_archive_events"]
    assert lib["uploads_enabled"] is True
    assert lib["incoming_materials_enabled"] is True
    assert lib["sha256_deduplication"] is True
    assert lib["cataloging_desk_enabled"] is True
    assert lib["librarian_agent_enabled"] is True
    assert "not a trusted Library item" in readme
    assert "does not appear in Card Catalog search" in readme


def test_v0865_cataloging_desk_promotes_file_human_only_and_survives_reset(tmp_path):
    import asyncio
    import app as campus
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.init_db()
        before_calls = 0
        with campus.db() as conn:
            before_calls = int(conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0])

        collection = asyncio.run(campus.api_library_collection_create(campus.LibraryCollectionRequest(
            title="Tinctures 101", collection_type="Class", subject="Herbalism", description="Past and current class editions"
        )))
        payload = b"%PDF-1.4\nCataloging Desk fixture\n%%EOF\n"
        uploaded = asyncio.run(campus.api_library_inbox_upload(
            _v0865_request(payload, "application/pdf"), filename="Tinctures Worksheet 2024.pdf"
        ))
        inbox_id = int(uploaded["inbox_id"])
        with campus.db() as conn:
            incoming = conn.execute("SELECT * FROM library_inbox WHERE id=?", (inbox_id,)).fetchone()
            incoming_path = campus.library_inbox_root() / incoming["stored_filename"]
            assert incoming_path.is_file()
            assert conn.execute("SELECT COUNT(*) FROM library_materials").fetchone()[0] == 0

        promoted = asyncio.run(campus.api_library_inbox_catalog(inbox_id, campus.LibraryCatalogRequest(
            collection_id=int(collection["collection_id"]),
            title="Tinctures 101 Student Worksheet",
            material_type="Worksheet",
            edition_label="2024 Edition",
            edition_date="2024-08-10",
            notes="Past class worksheet reviewed by human before cataloging.",
        )))
        assert promoted["trusted"] is True
        assert promoted["additional_ai_calls"] == 0
        material_id = int(promoted["material_id"])

        with campus.db() as conn:
            row = conn.execute("SELECT * FROM library_materials WHERE id=?", (material_id,)).fetchone()
            assert row["status"] == "Cataloged"
            assert row["material_type"] == "Worksheet"
            assert row["source_kind"] == "library_inbox"
            assert row["inbox_id"] == inbox_id
            assert row["sha256"] == uploaded["sha256"]
            trusted_path = (campus.DB_PATH.parent / row["relative_path"])
            assert trusted_path.is_file()
            assert trusted_path.read_bytes() == payload
            assert not incoming_path.exists()
            inbox = conn.execute("SELECT status,cataloged_material_id,cataloged_at FROM library_inbox WHERE id=?", (inbox_id,)).fetchone()
            assert inbox["status"] == "Cataloged"
            assert int(inbox["cataloged_material_id"]) == material_id
            assert inbox["cataloged_at"]
            assert int(conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]) == before_calls
            assert campus.library_foundation_summary(conn)["incoming_materials"] == 0
            assert campus.library_foundation_summary(conn)["materials"] == 1

        state = campus.current_state()
        assert state["library_inbox"] == []
        assert len(state["library_materials"]) == 1
        assert state["library_materials"][0]["collection_title"] == "Tinctures 101"
        catalog = asyncio.run(campus.api_library_catalog(q="Tinctures", collection_type="Class", status="Active"))
        assert catalog["count"] == 1
        assert int(catalog["collections"][0]["material_count"]) == 1

        asyncio.run(campus.api_reset())
        with campus.db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM library_materials WHERE status='Cataloged'").fetchone()[0] == 1
            row = conn.execute("SELECT relative_path FROM library_materials WHERE id=?", (material_id,)).fetchone()
            assert (campus.DB_PATH.parent / row["relative_path"]).is_file()
    finally:
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v0865_upgrade_helper_import_backup_restore_keeps_new_code_and_excludes_env(tmp_path):
    import importlib.util
    import zipfile

    helper_path = ROOT / "upgrade_helper.py"
    spec = importlib.util.spec_from_file_location("mavis_upgrade_helper_test", helper_path)
    helper = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(helper)

    old = tmp_path / "old-campus"
    new = tmp_path / "new-campus"
    restore = tmp_path / "restore-campus"
    for folder in (old, new, restore):
        folder.mkdir()
    (old / "mavis.db").write_bytes(b"old database")
    (old / ".env").write_text("OPENAI_API_KEY=secret-test-key\nGOOGLE_CALENDAR_CLIENT_ID=google-client-secret\nGOOGLE_CALENDAR_CLIENT_SECRET=google-secret\n", encoding="utf-8")
    (old / ".google-calendar-token.json").write_text('{"refresh_token":"google-refresh-secret"}', encoding="utf-8")
    (old / "repository").mkdir(); (old / "repository" / "project.md").write_text("project", encoding="utf-8")
    (old / "library").mkdir(); (old / "library" / "inbox").mkdir(); (old / "library" / "inbox" / "class.pdf").write_bytes(b"pdf")
    (old / "app.py").write_text("OLD APPLICATION CODE", encoding="utf-8")
    (new / "app.py").write_text("NEW APPLICATION CODE", encoding="utf-8")

    helper.BACKUP_DIR = tmp_path / "backups"
    helper.import_previous(old, new)
    assert (new / "mavis.db").read_bytes() == b"old database"
    assert "secret-test-key" in (new / ".env").read_text(encoding="utf-8")
    assert "google-client-secret" not in (new / ".env").read_text(encoding="utf-8")
    assert "google-secret" not in (new / ".env").read_text(encoding="utf-8")
    assert not (new / ".google-calendar-token.json").exists()
    assert (new / "repository" / "project.md").read_text(encoding="utf-8") == "project"
    assert (new / "library" / "inbox" / "class.pdf").read_bytes() == b"pdf"
    assert (new / "app.py").read_text(encoding="utf-8") == "NEW APPLICATION CODE"

    backup = helper.make_backup(new)
    assert backup.is_file()
    with zipfile.ZipFile(backup) as zf:
        names = set(zf.namelist())
        assert "mavis.db" in names
        assert "repository/project.md" in names
        assert "library/inbox/class.pdf" in names
        assert "backup-manifest.json" in names
        assert ".env" not in names
        assert ".google-calendar-token.json" not in names
        assert "app.py" not in names
        manifest = zf.read("backup-manifest.json").decode("utf-8")
        assert "Google Calendar OAuth token are intentionally excluded" in manifest

    helper.BACKUP_DIR = tmp_path / "restore-backups"
    (restore / "app.py").write_text("RESTORE APPLICATION CODE", encoding="utf-8")
    helper.restore_backup(backup, restore)
    assert (restore / "mavis.db").read_bytes() == b"old database"
    assert (restore / "repository" / "project.md").is_file()
    assert (restore / "library" / "inbox" / "class.pdf").is_file()
    assert not (restore / ".env").exists()
    assert (restore / "app.py").read_text(encoding="utf-8") == "RESTORE APPLICATION CODE"

    assert (ROOT / "IMPORT DATA FROM PREVIOUS VERSION.bat").is_file()
    assert (ROOT / "MAKE UPGRADE BACKUP.bat").is_file()
    assert (ROOT / "RESTORE UPGRADE BACKUP.bat").is_file()


def test_v0865_librarian_retrieves_trusted_active_library_only(tmp_path):
    import asyncio
    import app as campus
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.init_db()
        now = campus.utc_now()
        with campus.db() as conn:
            active_id = conn.execute(
                "INSERT INTO library_collections(title,collection_type,subject,description,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                ("Tinctures 101", "Class", "Herbalism", "Mavis tincture class", "Active", "Human", now, now),
            ).lastrowid
            archived_id = conn.execute(
                "INSERT INTO library_collections(title,collection_type,subject,description,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                ("Tinctures Old Draft", "Class", "Herbalism", "Archived class", "Archived", "Human", now, now),
            ).lastrowid
            conn.execute(
                "INSERT INTO library_materials(collection_id,title,material_type,edition_label,edition_date,status,source_kind,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (active_id, "Student Worksheet", "Worksheet", "2026", "2026-08-01", "Cataloged", "manual", "Tincture worksheet", "Human", now, now),
            )
            conn.execute(
                "INSERT INTO library_materials(collection_id,title,material_type,edition_label,edition_date,status,source_kind,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (archived_id, "Archived Tincture Notes", "Instructor Notes", "old", None, "Cataloged", "manual", "Should not be returned", "Human", now, now),
            )
            conn.execute(
                "INSERT INTO library_inbox(original_filename,stored_filename,relative_path,mime_type,size_bytes,sha256,status,source_kind,notes,created_by,received_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                ("Tinctures Secret Incoming.pdf", "incoming.pdf", "library/inbox/incoming.pdf", "application/pdf", 10, "a"*64, "Incoming", "upload", "Must stay quarantined", "Human", now, now),
            )
            before_ai = conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]

        result = asyncio.run(campus.api_library_librarian("tinctures"))
        assert result["status"] == "found"
        assert result["local_only"] is True
        assert result["trusted_library_only"] is True
        assert result["incoming_materials_excluded"] is True
        assert result["web_access"] is False
        assert result["additional_ai_calls"] == 0
        assert any(item["title"] == "Tinctures 101" for item in result["collections"])
        assert all(item["title"] != "Tinctures Old Draft" for item in result["collections"])
        assert any(item["title"] == "Student Worksheet" for item in result["materials"])
        assert all("Incoming" not in str(item.get("title", "")) for item in result["materials"])
        with campus.db() as conn:
            after_ai = conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]
        assert before_ai == after_ai == 0
    finally:
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v0865_librarian_no_match_recommends_research(tmp_path):
    import asyncio
    import app as campus
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.init_db()
        result = asyncio.run(campus.api_library_librarian("quantum beekeeping on mars"))
        assert result["status"] == "not_found"
        assert result["collections"] == []
        assert result["materials"] == []
        assert result["external_research_recommended"] is True
        assert result["web_access"] is False
        assert "Research" in result["message"]
    finally:
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v0865_librarian_has_hard_local_boundary_and_ui_contract():
    import json
    source = (ROOT / "agents/librarian.py").read_text(encoding="utf-8")
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    data = json.loads((ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8"))
    for forbidden in ("import requests", "import httpx", "import urllib", "import socket", "from ai.", "import ai."):
        assert forbidden not in source
    assert '@app.get("/api/library/librarian")' in app_text
    assert "data-librarian-form" in js
    assert "/api/library/librarian" in js
    assert "The Librarian will not search the web" in js
    lib = data["library_foundation"]
    assert lib["librarian_agent_enabled"] is True
    assert lib["librarian_retrieval_enabled"] is True
    assert lib["librarian_web_access"] is False
    assert lib["librarian_trusted_library_only"] is True
    assert lib["librarian_incoming_materials_excluded"] is True


def test_v0866_chief_duplicate_request_protection_one_project_one_ai_call(tmp_path):
    import asyncio
    import time as _time
    from types import SimpleNamespace
    from ai.provider import GenerationResult

    original_db = campus.DB_PATH
    original_workflow = campus.workflow_task
    original_lock = campus.chief_plan_lock
    original_role_provider_id = campus.role_provider_id
    original_provider_status = campus.provider_public_status
    original_get_role_provider = campus.get_role_provider
    original_plan_project = campus.plan_project
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.init_db()
        campus.workflow_task = None
        calls = {"count": 0}

        campus.role_provider_id = lambda role: "gemini"
        campus.provider_public_status = lambda provider_id: {
            "configured": True, "provider": "Gemini", "model": "fake-gemini"
        }
        campus.get_role_provider = lambda role: object()

        def fake_plan_project(provider, request, memory_context, playbook_context):
            calls["count"] += 1
            _time.sleep(0.05)
            plan = {
                "project_title": "Duplicate Protection Test",
                "summary": "One Chief plan should be created.",
                "success_criteria": ["One project"],
                "tasks": [
                    {"title": "Research", "owner": "research", "brief": "Research the request."},
                    {"title": "Build", "owner": "programs", "brief": "Build the program."},
                    {"title": "Review", "owner": "chief", "brief": "Review the package."},
                ],
                "questions_for_executive": [],
                "risk_notes": [],
                "expected_deliverables": [],
            }
            generation = GenerationResult(
                provider="gemini", model="fake-gemini", text="{}",
                input_chars=len(request), output_chars=2,
            )
            return SimpleNamespace(plan=plan, generation=generation)

        campus.plan_project = fake_plan_project

        async def run_test():
            campus.chief_plan_lock = asyncio.Lock()
            a, b = await asyncio.gather(
                campus.api_chief_plan(campus.ProjectRequest(
                    title="Build a tincture class", request_id="submit-a"
                )),
                campus.api_chief_plan(campus.ProjectRequest(
                    title="  build   a TINCTURE class  ", request_id="submit-b"
                )),
            )
            return a, b

        first, second = asyncio.run(run_test())
        assert first["project_id"] == second["project_id"]
        assert sorted([first["duplicate_prevented"], second["duplicate_prevented"]]) == [False, True]
        assert calls["count"] == 1
        with campus.db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM ai_calls WHERE operation='chief_plan' AND status='Success'").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM chief_request_submissions WHERE status='Completed'").fetchone()[0] == 1
    finally:
        campus.plan_project = original_plan_project
        campus.get_role_provider = original_get_role_provider
        campus.provider_public_status = original_provider_status
        campus.role_provider_id = original_role_provider_id
        campus.chief_plan_lock = original_lock
        campus.workflow_task = original_workflow
        campus.DB_PATH = original_db


def test_v0866_chief_force_new_is_explicit_and_still_respects_human_gate(tmp_path):
    import asyncio
    from types import SimpleNamespace
    from ai.provider import GenerationResult

    original_db = campus.DB_PATH
    original_workflow = campus.workflow_task
    original_lock = campus.chief_plan_lock
    original_role_provider_id = campus.role_provider_id
    original_provider_status = campus.provider_public_status
    original_get_role_provider = campus.get_role_provider
    original_plan_project = campus.plan_project
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.init_db()
        campus.workflow_task = None
        calls = {"count": 0}
        campus.role_provider_id = lambda role: "gemini"
        campus.provider_public_status = lambda provider_id: {"configured": True, "provider": "Gemini", "model": "fake"}
        campus.get_role_provider = lambda role: object()
        def fake_plan_project(provider, request, memory_context, playbook_context):
            calls["count"] += 1
            return SimpleNamespace(
                plan={
                    "project_title": f"Plan {calls['count']}", "summary": "Summary",
                    "success_criteria": [],
                    "tasks":[
                        {"title":"Research","owner":"research","brief":"Research"},
                        {"title":"Build","owner":"programs","brief":"Build"},
                        {"title":"Review","owner":"chief","brief":"Review"},
                    ],
                    "questions_for_executive": [], "risk_notes": [], "expected_deliverables": [],
                },
                generation=GenerationResult(provider="gemini",model="fake",text="{}",input_chars=len(request),output_chars=2),
            )
        campus.plan_project = fake_plan_project

        async def run_test():
            campus.chief_plan_lock = asyncio.Lock()
            first = await campus.api_chief_plan(campus.ProjectRequest(title="Same request", request_id="one"))
            # A forced rerun cannot bypass the existing human approval gate.
            try:
                await campus.api_chief_plan(campus.ProjectRequest(title="Same request", request_id="two", force_new=True))
                assert False, "force_new must not bypass pending human approval"
            except campus.HTTPException as exc:
                assert exc.status_code == 409
            with campus.db() as conn:
                conn.execute("DELETE FROM approvals WHERE status='Pending'")
                conn.execute("UPDATE projects SET status='Completed' WHERE id=?", (first["project_id"],))
            second = await campus.api_chief_plan(campus.ProjectRequest(title="Same request", request_id="three", force_new=True))
            return first, second

        first, second = asyncio.run(run_test())
        assert first["project_id"] != second["project_id"]
        assert calls["count"] == 2
    finally:
        campus.plan_project = original_plan_project
        campus.get_role_provider = original_get_role_provider
        campus.provider_public_status = original_provider_status
        campus.role_provider_id = original_role_provider_id
        campus.chief_plan_lock = original_lock
        campus.workflow_task = original_workflow
        campus.DB_PATH = original_db


def test_v0866_programs_library_first_pauses_before_ai_then_reuses_locally(tmp_path):
    import asyncio
    import json
    import app as campus
    original_db, original_repo, original_pause = campus.DB_PATH, campus.REPOSITORY, campus.pause
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        async def no_pause(_seconds):
            return None
        campus.pause = no_pause
        campus.init_db()
        now = campus.utc_now()
        with campus.db() as conn:
            project_id = int(conn.execute(
                "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                ("Build a tinctures class", "Active", now, now),
            ).lastrowid)
            task_id = int(conn.execute(
                "INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (project_id, "Create a tinctures class", "programs", "Waiting", 1, "Create a practical tinctures workshop.", now, now),
            ).lastrowid)
            collection_id = int(conn.execute(
                "INSERT INTO library_collections(title,collection_type,subject,description,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                ("Tinctures 101", "Class", "Herbalism tinctures", "Approved Mavis tincture class", "Active", "Human", now, now),
            ).lastrowid)
            trusted_dir = campus.library_catalog_root() / f"collection-{collection_id:04d}"
            trusted_dir.mkdir(parents=True, exist_ok=True)
            trusted_file = trusted_dir / "tinctures-worksheet.pdf"
            trusted_file.write_bytes(b"%PDF-trusted-tinctures")
            relative_path = trusted_file.resolve().relative_to(campus.DB_PATH.parent.resolve()).as_posix()
            conn.execute(
                """INSERT INTO library_materials(
                    collection_id,title,material_type,status,source_kind,notes,created_by,created_at,updated_at,
                    original_filename,stored_filename,relative_path,mime_type,size_bytes,sha256
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (collection_id, "Tinctures Student Worksheet", "Worksheet", "Cataloged", "library_inbox", "Trusted worksheet", "Human", now, now,
                 "Tinctures Worksheet.pdf", trusted_file.name, relative_path, "application/pdf", trusted_file.stat().st_size, "e"*64),
            )
            conn.execute(
                "INSERT INTO library_inbox(original_filename,stored_filename,relative_path,mime_type,size_bytes,sha256,status,source_kind,notes,created_by,received_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                ("Tinctures Secret Incoming.pdf", "incoming.pdf", "library/inbox/incoming.pdf", "application/pdf", 10, "f"*64, "Incoming", "upload", "Must remain quarantined", "Human", now, now),
            )
            before_ai = int(conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0])

        asyncio.run(campus.execute_approved_plan(project_id))
        with campus.db() as conn:
            task = conn.execute("SELECT status,result FROM tasks WHERE id=?", (task_id,)).fetchone()
            project = conn.execute("SELECT status FROM projects WHERE id=?", (project_id,)).fetchone()
            pf = conn.execute("SELECT * FROM programs_library_preflights WHERE task_id=?", (task_id,)).fetchone()
            result = json.loads(pf["result_json"])
            assert task["status"] == "Library Review"
            assert project["status"] == "Awaiting Library Decision"
            assert pf["status"] == "Pending" and pf["decision"] == ""
            assert any(x["title"] == "Tinctures 101" for x in result["collections"])
            assert any(x["title"] == "Tinctures Student Worksheet" for x in result["materials"])
            assert "Incoming" not in json.dumps(result)
            assert int(conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]) == before_ai == 0
            executive = campus.executive_summary(conn)
            assert executive["library_decisions"] == 1
            assert any(item["kind"] == "library_first" and int(item["task_id"]) == task_id for item in executive["attention"])

            conn.execute(
                "UPDATE programs_library_preflights SET status='Decided',decision='reuse',selected_collection_id=?,updated_at=? WHERE task_id=?",
                (collection_id, campus.utc_now(), task_id),
            )
            conn.execute("UPDATE tasks SET status='Waiting',result=NULL,updated_at=? WHERE id=?", (campus.utc_now(), task_id))
            conn.execute("UPDATE projects SET status='Active',updated_at=? WHERE id=?", (campus.utc_now(), project_id))

        asyncio.run(campus.execute_approved_plan(project_id, resume=True))
        with campus.db() as conn:
            task = conn.execute("SELECT status,result FROM tasks WHERE id=?", (task_id,)).fetchone()
            assert task["status"] == "Completed"
            assert "reused trusted Library collection 'Tinctures 101'" in task["result"]
            assert conn.execute("SELECT COUNT(*) FROM deliverables WHERE project_id=?", (project_id,)).fetchone()[0] >= 1
            assert conn.execute("SELECT COUNT(*) FROM project_files WHERE project_id=? AND created_by='Library reuse / Human'", (project_id,)).fetchone()[0] == 2
            reused = conn.execute("SELECT relative_path FROM project_files WHERE project_id=? AND created_by='Library reuse / Human' AND file_kind='pdf'", (project_id,)).fetchone()
            assert reused and (campus.REPOSITORY / reused["relative_path"]).is_file()
            assert int(conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]) == 0
    finally:
        campus.pause = original_pause
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v0866_programs_library_first_no_match_allows_create_new_without_librarian_ai(tmp_path):
    import app as campus
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.init_db()
        now = campus.utc_now()
        with campus.db() as conn:
            project_id = int(conn.execute(
                "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                ("Quantum beekeeping on Mars", "Active", now, now),
            ).lastrowid)
            task_id = int(conn.execute(
                "INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (project_id, "Create Mars bee class", "programs", "Waiting", 1, "Build a quantum Mars beekeeping class.", now, now),
            ).lastrowid)
            project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            pf = campus.ensure_programs_library_preflight(conn, project=project, task=task)
            assert pf["status"] == "No Match"
            assert pf["decision"] == "create_new"
            assert pf["result"]["status"] == "not_found"
            assert pf["result"]["web_access"] is False
            assert int(conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]) == 0
    finally:
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v0867_programs_revision_can_receive_trusted_indexed_text_and_ui_contract():
    import json
    from ai.provider import GenerationResult
    from agents.programs import run_programs

    captured = {}
    class Provider:
        def generate_structured(self, prompt, schema_name, schema, max_output_tokens):
            captured["prompt"] = prompt
            artifact = {
                "deliverable_title":"Revised Tinctures 101",
                "program_summary":"A revised practical tincture class.",
                "audience":"Adults and teens",
                "duration_minutes":45,
                "objectives":["Prepare a clearly labeled practice tincture."],
                "run_of_show":[{"minutes":45,"segment":"Workshop","purpose":"Practice the method","facilitator_action":"Demonstrate and guide practice."}],
                "materials":[],"participant_activities":[],"facilitator_notes":[],"handout_or_resource_ideas":[],
                "research_integration":[],"verification_flags":[],"handoff_note":"Review before teaching."
            }
            text=json.dumps(artifact)
            return GenerationResult(provider="fake",model="fake",text=text,input_chars=len(prompt),output_chars=len(text))

    context = {
        "decision":"revise",
        "query":"tinctures herbalism",
        "selected_collection":{"id":7,"title":"Tinctures 101","subject":"Herbalism"},
        "selected_materials":[{"title":"2026 Slideshow","material_type":"Slideshow","index_status":"indexed"}],
        "selected_material_contents":[{"material_id":9,"title":"2026 Slideshow","material_type":"Slideshow","trusted_local_text":"Safety before extraction. Label every jar clearly."}],
        "file_contents_supplied":True,
    }
    result = run_programs(
        Provider(), project_title="Revise Tinctures", project_summary="Update the class",
        task_title="Revise class", task_brief="Create the next edition",
        library_context=context,
    )
    assert result.artifact["deliverable_title"] == "Revised Tinctures 101"
    assert "PROGRAMS LIBRARY FIRST" in captured["prompt"]
    assert '"decision": "revise"' in captured["prompt"]
    assert '"title": "Tinctures 101"' in captured["prompt"]
    assert "only claim to have read file content" in captured["prompt"].lower()
    assert "Safety before extraction" in captured["prompt"]

    js=(ROOT / "static/js/app.js").read_text(encoding="utf-8")
    manifest=json.loads((ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8"))
    assert 'data-programs-library-choice="reuse"' in js
    assert 'data-programs-library-choice="revise"' in js
    assert 'data-programs-library-choice="create_new"' in js
    assert '/api/programs/library-first/' in js
    lib=manifest["library_foundation"]
    assert lib["programs_library_first_enabled"] is True
    assert lib["programs_library_first_human_choice"] is True
    assert lib["programs_library_first_web_access"] is False
    assert lib["programs_reuse_without_ai"] is True


def test_v0866_library_first_human_decision_endpoint_records_choice_and_resumes(tmp_path):
    import asyncio
    import json
    import app as campus
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    original_workflow, original_execute = campus.workflow_task, campus.execute_approved_plan
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.workflow_task = None
        campus.init_db()
        now=campus.utc_now()
        with campus.db() as conn:
            pid=int(conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",("Tinctures","Awaiting Library Decision",now,now)).lastrowid)
            tid=int(conn.execute("INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(pid,"Build tinctures","programs","Library Review",1,"Build tinctures",now,now)).lastrowid)
            cid=int(conn.execute("INSERT INTO library_collections(title,collection_type,subject,description,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",("Tinctures 101","Class","Herbalism","Trusted","Active","Human",now,now)).lastrowid)
            result={"collections":[{"id":cid,"title":"Tinctures 101"}],"materials":[]}
            conn.execute("INSERT INTO programs_library_preflights(task_id,project_id,query,result_json,status,decision,selected_collection_id,human_note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(tid,pid,"tinctures",json.dumps(result),"Pending","",None,"",now,now))
        called=[]
        async def fake_execute(project_id, *, resume=False, revision=False):
            called.append((project_id,resume,revision))
        campus.execute_approved_plan=fake_execute
        async def run():
            result=await campus.api_programs_library_first_decide(tid,campus.ProgramsLibraryDecisionRequest(decision="revise",collection_id=cid,note="Keep the safe labeling section."))
            if campus.workflow_task:
                await campus.workflow_task
            return result
        result=asyncio.run(run())
        assert result["decision"]=="revise" and result["selected_collection_id"]==cid
        assert called==[(pid,True,False)]
        with campus.db() as conn:
            pf=conn.execute("SELECT * FROM programs_library_preflights WHERE task_id=?",(tid,)).fetchone()
            task=conn.execute("SELECT status FROM tasks WHERE id=?",(tid,)).fetchone()
            assert pf["status"]=="Decided" and pf["decision"]=="revise"
            assert pf["human_note"]=="Keep the safe labeling section."
            assert task["status"]=="Waiting"
    finally:
        campus.execute_approved_plan=original_execute
        campus.workflow_task=original_workflow
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v0867_trusted_document_text_is_indexed_and_librarian_searches_inside_file(tmp_path):
    import app as campus
    from agents.librarian import search_trusted_library
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.init_db()
        now = campus.utc_now()
        with campus.db() as conn:
            cid = int(conn.execute(
                "INSERT INTO library_collections(title,collection_type,subject,description,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                ("Tree Crop Notes", "Class", "Permaculture", "General tree crop class", "Active", "Human", now, now),
            ).lastrowid)
            folder = campus.library_catalog_root() / f"collection-{cid}"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "notes.txt"
            path.write_text("Use cold stratification for pawpaw seed before spring germination.", encoding="utf-8")
            rel = path.relative_to(campus.DB_PATH.parent).as_posix()
            mid = int(conn.execute(
                """INSERT INTO library_materials(collection_id,title,material_type,status,source_kind,notes,created_by,created_at,updated_at,original_filename,stored_filename,relative_path,mime_type,size_bytes,sha256)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (cid,"Historical Notes","Instructor Notes","Cataloged","manual","","Human",now,now,"notes.txt","notes.txt",rel,"text/plain",path.stat().st_size,"sha-text-0867"),
            ).lastrowid)
            indexed = campus.index_library_material(conn, mid, force=True)
            assert indexed["extraction_status"] == "indexed"
            assert indexed["char_count"] > 20
            result = search_trusted_library("pawpaw", campus.library_catalog_rows(conn), campus.library_material_search_rows(conn))
            assert result["status"] == "found"
            hit = next(item for item in result["materials"] if int(item["id"]) == mid)
            assert hit["content_indexed"] is True
            assert "pawpaw" in hit["content_match_excerpt"].lower()
            assert "indexed_text" not in hit
            assert conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0] == 0
    finally:
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v0867_incoming_material_is_never_indexed_or_retrieved(tmp_path):
    import app as campus
    from agents.librarian import search_trusted_library
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.init_db()
        inbox = campus.library_inbox_root()
        incoming_path = inbox / "incoming-secret.txt"
        incoming_path.write_text("quarantineonlykeyword should never reach the Librarian", encoding="utf-8")
        now = campus.utc_now()
        with campus.db() as conn:
            conn.execute(
                """INSERT INTO library_inbox(original_filename,stored_filename,relative_path,mime_type,size_bytes,sha256,status,source_kind,notes,created_by,received_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("incoming-secret.txt",incoming_path.name,incoming_path.relative_to(campus.DB_PATH.parent).as_posix(),"text/plain",incoming_path.stat().st_size,"incoming-sha-0867","Incoming","upload","","Human",now,now),
            )
            refreshed = campus.refresh_library_index(conn, force=True)
            assert refreshed["materials_checked"] == 0
            assert conn.execute("SELECT COUNT(*) FROM library_material_index").fetchone()[0] == 0
            result = search_trusted_library("quarantineonlykeyword", campus.library_catalog_rows(conn), campus.library_material_search_rows(conn))
            assert result["status"] == "not_found"
            assert result["incoming_materials_excluded"] is True
            assert result["web_access"] is False
            assert result["additional_ai_calls"] == 0
    finally:
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v0867_programs_revision_context_contains_only_trusted_bounded_indexed_text(tmp_path):
    import json
    import app as campus
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.init_db()
        now = campus.utc_now()
        with campus.db() as conn:
            pid = int(conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)", ("Revise class","Active",now,now)).lastrowid)
            tid = int(conn.execute("INSERT INTO tasks(project_id,sequence,title,owner_agent_id,status,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (pid,1,"Revise program","programs","Waiting","Revise trusted class",now,now)).lastrowid)
            cid = int(conn.execute("INSERT INTO library_collections(title,collection_type,subject,description,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", ("Seed Saving 101","Class","Seeds","Trusted baseline","Active","Human",now,now)).lastrowid)
            folder = campus.library_catalog_root() / f"collection-{cid}"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "baseline.md"
            trusted_text = "Preserve Appalachian seed stories and include a hands-on dry seed cleaning activity."
            path.write_text(trusted_text, encoding="utf-8")
            mid = int(conn.execute("""INSERT INTO library_materials(collection_id,title,material_type,status,source_kind,created_by,created_at,updated_at,original_filename,stored_filename,relative_path,mime_type,size_bytes,sha256)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (cid,"Baseline","Lesson Plan","Cataloged","manual","Human",now,now,path.name,path.name,path.relative_to(campus.DB_PATH.parent).as_posix(),"text/markdown",path.stat().st_size,"program-sha-0867")).lastrowid)
            campus.index_library_material(conn, mid, force=True)
            result = {"status":"found","collections":[{"id":cid,"title":"Seed Saving 101"}],"materials":[{"id":mid,"collection_id":cid,"title":"Baseline"}]}
            conn.execute("""INSERT INTO programs_library_preflights(task_id,project_id,query,result_json,status,decision,selected_collection_id,human_note,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", (tid,pid,"seed saving",json.dumps(result),"Decided","revise",cid,"Preserve Appalachian framing",now,now))
            context = campus.programs_library_context_for_task(conn, tid)
            assert context["file_contents_supplied"] is True
            assert context["incoming_materials_excluded"] is True
            assert context["supplied_text_characters"] == len(trusted_text)
            assert context["selected_material_contents"][0]["trusted_local_text"] == trusted_text
            assert context["selected_material_contents"][0]["material_id"] == mid
    finally:
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def _v08698_seed_programs_final_review(campus, *, project_title="Seed Saving Workshop", collection_id=None, preflight_decision=None):
    now = campus.utc_now()
    with campus.db() as conn:
        project_id = int(conn.execute(
            "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
            (project_title,"Awaiting Execution Review",now,now),
        ).lastrowid)
        task_id = int(conn.execute(
            """
            INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,result,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (project_id,"Build the class","programs","Completed",1,"Build a practical class.","Programs complete.",now,now),
        ).lastrowid)
        deliverable_ids = []
        for dtype,title,body in [
            ("lesson_plan",f"{project_title} — Lesson Plan","# Lesson Plan\n\nTeach seed saving with dry bean and tomato examples."),
            ("participant_handout",f"{project_title} — Handout","# Handout\n\nKeep seed dry, cool, dark, and clearly labeled."),
        ]:
            deliverable_ids.append(campus.upsert_deliverable(
                conn, project_id=project_id, source_task_id=task_id, deliverable_type=dtype,
                title=title, purpose="Test approved Programs output.", content_md=body,
                created_by="Programs", provider="test", model="test-model", verification_items=[], status="Draft",
            ))
        if preflight_decision:
            conn.execute(
                """
                INSERT INTO programs_library_preflights(
                    task_id,project_id,query,result_json,status,decision,selected_collection_id,human_note,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (task_id,project_id,"seed saving","{}","Decided",preflight_decision,collection_id,"",now,now),
            )
        approval_id = int(conn.execute(
            "INSERT INTO approvals(project_id,title,summary,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (project_id,f"Chief final review: {project_title}","Final package ready.","Pending",now,now),
        ).lastrowid)
        conn.execute(
            "INSERT INTO workflow_runs(project_id,state,current_task_id,last_error,retry_count,updated_at) VALUES(?,?,?,?,?,?)",
            (project_id,"Awaiting Human Review",None,None,0,now),
        )
    return project_id, task_id, deliverable_ids, approval_id


def test_v08698_final_human_approval_auto_archives_programs_outputs(tmp_path):
    import asyncio
    import app as campus
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.init_db()
        project_id, task_id, deliverable_ids, approval_id = _v08698_seed_programs_final_review(campus)

        with campus.db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM library_materials").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM program_archive_events").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0] == 0

        result = asyncio.run(campus.api_approval_decide(
            approval_id, campus.ApprovalDecision(decision="approve", note="Approved for institutional use.")
        ))
        assert result["project_completed"] is True
        archive = result["programs_auto_archive"]
        assert archive["status"] == "Archived"
        assert archive["material_count"] == 2
        assert archive["additional_ai_calls"] == 0
        assert archive["web_access"] is False

        with campus.db() as conn:
            collection = conn.execute("SELECT * FROM library_collections").fetchone()
            assert collection["title"] == "Seed Saving Workshop"
            assert collection["collection_type"] == "Class"
            mats = conn.execute(
                "SELECT * FROM library_materials ORDER BY material_type,title"
            ).fetchall()
            assert len(mats) == 2
            assert {m["source_kind"] for m in mats} == {"programs_auto_archive"}
            assert {int(m["source_project_id"]) for m in mats} == {project_id}
            assert {int(m["source_deliverable_id"]) for m in mats} == set(deliverable_ids)
            assert all(str(m["edition_label"]).startswith("Approved ") for m in mats)
            assert all((campus.DB_PATH.parent / m["relative_path"]).is_file() for m in mats)
            indexed = conn.execute(
                "SELECT COUNT(*) FROM library_material_index WHERE extraction_status='indexed'"
            ).fetchone()[0]
            assert indexed == 2
            assert conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0] == 0
            event = conn.execute("SELECT * FROM program_archive_events").fetchone()
            assert event["status"] == "Archived" and event["material_count"] == 2
            assert int(event["source_approval_id"]) == approval_id
            assert campus.library_foundation_summary(conn)["program_auto_archive_events"] == 1

        # Same approval is idempotent at the archive layer.
        with campus.db() as conn:
            again = campus.archive_approved_programs_project(conn, project_id=project_id, approval_id=approval_id)
            assert again["idempotent"] is True
            assert conn.execute("SELECT COUNT(*) FROM library_materials").fetchone()[0] == 2

        # Durable Library and archive audit survive the demo reset even though project workspace does not.
        campus.reset_runtime()
        with campus.db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM library_materials").fetchone()[0] == 2
            assert conn.execute("SELECT COUNT(*) FROM program_archive_events").fetchone()[0] == 1
    finally:
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v08698_changes_requested_does_not_archive_draft_programs_work(tmp_path):
    import asyncio
    import app as campus
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.init_db()
        project_id, task_id, deliverable_ids, approval_id = _v08698_seed_programs_final_review(campus, project_title="Biochar Basics")
        result = asyncio.run(campus.api_approval_decide(
            approval_id, campus.ApprovalDecision(decision="changes", note="Tighten the safety section first.")
        ))
        assert result["project_completed"] is False
        assert result["programs_auto_archive"] is None
        with campus.db() as conn:
            assert conn.execute("SELECT COUNT(*) FROM library_collections").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM library_materials").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM program_archive_events").fetchone()[0] == 0
            assert conn.execute("SELECT status FROM projects WHERE id=?",(project_id,)).fetchone()[0] == "Needs Revision"
    finally:
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v08698_revision_archives_into_selected_collection_without_duplicating_old_outputs(tmp_path):
    import app as campus
    original_db, original_repo = campus.DB_PATH, campus.REPOSITORY
    try:
        campus.DB_PATH = tmp_path / "mavis.db"
        campus.REPOSITORY = tmp_path / "repository"
        campus.init_db()
        now = campus.utc_now()
        with campus.db() as conn:
            collection_id = int(conn.execute(
                "INSERT INTO library_collections(title,collection_type,subject,description,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                ("Tinctures 101","Class","Herbal Skills","Established Mavis class.","Active","Human",now,now),
            ).lastrowid)
        project_id, task_id, deliverable_ids, approval_id = _v08698_seed_programs_final_review(
            campus, project_title="Tinctures 101 Update", collection_id=collection_id, preflight_decision="revise"
        )
        with campus.db() as conn:
            conn.execute("UPDATE deliverables SET status='Approved' WHERE project_id=?",(project_id,))
            first = campus.archive_approved_programs_project(conn, project_id=project_id, approval_id=approval_id)
            assert first["collection_id"] == collection_id
            assert first["material_count"] == 2
            # Simulate a later approved revision: preserve one existing deliverable ID and create one new Programs output version/ID.
            old_handout = conn.execute(
                "SELECT * FROM deliverables WHERE id=?",(deliverable_ids[1],)
            ).fetchone()
            new_id = int(conn.execute(
                """
                INSERT INTO deliverables(project_id,source_task_id,deliverable_key,deliverable_type,title,purpose,status,content_md,version,created_by,provider,model,verification_json,chief_review_status,chief_review_note,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (project_id,task_id,"lesson_plan:revision","lesson_plan","Tinctures 101 — Revised Lesson Plan","Revision","Approved","# Revised\n\nUpdated dosage-claim caution and labeling activity.",2,"Programs","test","test-model","[]",None,None,now,now),
            ).lastrowid)
            second = campus.archive_approved_programs_project(conn, project_id=project_id, approval_id=approval_id+1000)
            assert second["collection_id"] == collection_id
            assert second["material_count"] == 1
            assert second["skipped_count"] == 2
            assert new_id in second["material_ids"] or conn.execute(
                "SELECT source_deliverable_id FROM library_materials WHERE id=?",(second["material_ids"][0],)
            ).fetchone()[0] == new_id
            assert conn.execute("SELECT COUNT(*) FROM library_materials WHERE collection_id=?",(collection_id,)).fetchone()[0] == 3
    finally:
        campus.DB_PATH, campus.REPOSITORY = original_db, original_repo


def test_v08698_manifest_and_archive_boundary():
    import json
    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    data = json.loads((ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8"))
    assert LIVE_SHELL_LABEL in index
    assert f"app.js?v={LIVE_CACHE_KEY}" in index and f"app.css?v={LIVE_CACHE_KEY}" in index
    lib = data["library_foundation"]
    assert lib["phase"] == "programs_auto_archive"
    assert lib["program_auto_archive_enabled"] is True
    assert lib["program_auto_archive_final_human_approval_only"] is True
    assert lib["program_auto_archive_web_access"] is False
    assert lib["program_auto_archive_ai_calls"] == 0
    assert "program_archive_events" in lib["tables"]
    assert "Initial plan approval" in readme
    assert "zero AI calls and zero network calls" in readme
    assert "no direct web access" in readme


def test_v08698_world_shell_restored_and_cache_busted():
    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    assert 'id="buildings"' in index
    assert 'id="agents"' in index
    assert f'/static/css/world.css?v={LIVE_CACHE_KEY}' in index
    assert f'/static/js/app.js?v={LIVE_CACHE_KEY}' in index
    assert f"./world-config.js?v={LIVE_CACHE_KEY}" in js
    assert f"./world-assets.js?v={LIVE_CACHE_KEY}" in js
    assert 'function renderBuildings()' in js
    assert 'function renderAgents()' in js


def test_v08698_state_seeds_all_canonical_agents_and_buildings(tmp_path, monkeypatch):
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'hotfix.db')
    appmod.init_db()
    with appmod.db() as conn:
        appmod.seed_base(conn)
        agents = {row['id'] for row in conn.execute('SELECT id FROM agents').fetchall()}
        buildings = {row['id'] for row in conn.execute('SELECT id FROM buildings').fetchall()}
    assert agents == {'chief','programs','research','caretaker','operations','grants'}
    assert buildings == {'manor','library','barn','fruit_forest'}


def test_v08698_all_world_asset_targets_exist():
    import re
    js = (ROOT / 'static/js/world-assets.js').read_text(encoding='utf-8')
    paths = re.findall(r"['\"](/static/assets/[^'\"]+)['\"]", js)
    assert paths
    missing=[]
    for path in paths:
        local = ROOT / path.lstrip('/')
        if not local.exists():
            missing.append(path)
    assert missing == []


def test_v08698_pws_weather_defaults_and_separation(tmp_path, monkeypatch):
    import app as campus
    original = campus.DB_PATH
    campus.DB_PATH = tmp_path / "mavis.db"
    monkeypatch.setattr(campus, "weather_underground_key_available", lambda: False)
    try:
        campus.init_db()
        with campus.db() as conn:
            env = campus.environment_summary(conn)
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert campus.SCHEMA_VERSION == LIVE_VERSION
        assert {"environment_settings", "weather_current", "weather_daily", "seasonal_windows"}.issubset(tables)
        assert env["phase"] == "weather_seasons_pws"
        assert env["pws_station_id"] == "KWFLATT11"
        assert env["pws_provider"] == "Weather Underground"
        assert env["pws_api_key_configured"] is False
        assert env["pws_connection_status"] == "API key needed"
        assert env["weather_network_access"] is True
        assert env["librarian_network_access"] is False
        assert env["additional_ai_calls"] == 0
        assert env["calendar_integration_enabled"] is False
        assert env["automatic_rescheduling_enabled"] is False
    finally:
        campus.DB_PATH = original


def test_v08698_weather_refresh_persists_pws_and_forecast_without_ai(tmp_path):
    import app as campus
    original = campus.DB_PATH
    campus.DB_PATH = tmp_path / "mavis.db"
    try:
        campus.init_db()
        result = {
            "pws_connected": True,
            "errors": [],
            "current": {
                "source": "Weather Underground PWS", "source_kind": "personal_weather_station",
                "station_id": "KWFLATT11", "observed_at": "2026-08-31T18:00:00Z",
                "temperature_f": 71.2, "feels_like_f": 71.0, "humidity_pct": 68,
                "dewpoint_f": 60.0, "pressure_in": 30.01, "wind_mph": 4.2,
                "wind_gust_mph": 9.1, "wind_direction_deg": 215, "precip_rate_in": 0.0,
                "precip_total_in": 0.12, "solar_radiation": 220, "uv_index": 2.1,
                "summary": "Personal weather station observation", "latitude": 37.59, "longitude": -81.11,
            },
            "forecast": [{
                "forecast_date": "2099-09-01", "high_f": 75, "low_f": 58, "precip_chance": 20,
                "precip_total_in": 0.01, "rain_total_in": 0.01, "snow_total_in": 0,
                "wind_max_mph": 8, "wind_gust_max_mph": 14, "sunrise": "2099-09-01T06:55",
                "sunset": "2099-09-01T19:55", "daylight_seconds": 46800,
                "summary": "Partly cloudy", "source": "Open-Meteo",
            }],
        }
        with campus.db() as conn:
            before = conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]
            campus._store_weather_refresh(conn, result)
            after = conn.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0]
            current = conn.execute("SELECT * FROM weather_current WHERE id=1").fetchone()
            day = conn.execute("SELECT * FROM weather_daily WHERE forecast_date='2099-09-01'").fetchone()
        assert before == after == 0
        assert current["station_id"] == "KWFLATT11"
        assert current["source_kind"] == "personal_weather_station"
        assert current["temperature_f"] == 71.2
        assert day["source"] == "Open-Meteo"
        assert day["high_f"] == 75
    finally:
        campus.DB_PATH = original


def test_v08698_weather_provider_fallback_is_not_mislabeled_as_pws(monkeypatch):
    import weather_provider as wp
    monkeypatch.setattr(wp, "weather_underground_key_available", lambda: False)
    monkeypatch.setattr(wp, "fetch_open_meteo", lambda lat, lon, tz: {
        "current": {"source": "Open-Meteo", "source_kind": "model_fallback", "station_id": "", "temperature_f": 70, "summary": "Clear"},
        "forecast": [{"forecast_date": "2099-09-01", "source": "Open-Meteo"}],
    })
    result = wp.refresh_weather({"pws_station_id": "KWFLATT11", "latitude": 37.59, "longitude": -81.11, "timezone_name": "America/New_York"})
    assert result["pws_connected"] is False
    assert result["current"]["source_kind"] == "model_fallback"
    assert result["current"]["station_id"] == ""
    assert any("API key not configured" in item for item in result["errors"])


def test_v08698_weather_ui_keeps_known_good_world_modules_and_pws_controls():
    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    librarian = (ROOT / "agents/librarian.py").read_text(encoding="utf-8")
    assert 'data-panel="environment"' in index
    assert f"./world-config.js?v={LIVE_CACHE_KEY}" in js
    assert f"./world-assets.js?v={LIVE_CACHE_KEY}" in js
    assert "KWFLATT11" in js
    assert "data-weather-refresh" in js
    assert "WEATHER_UNDERGROUND_API_KEY" in js
    assert "weather_provider" not in librarian
    assert "urllib" not in librarian


def test_v08698_moon_cycle_is_local_and_bounded():
    from datetime import datetime, timezone
    import app as campus
    moon = campus.moon_cycle_summary(datetime(2026, 8, 31, 20, 0, tzinfo=timezone.utc))
    assert moon["phase"] in {"New Moon","Waxing Crescent","First Quarter","Waxing Gibbous","Full Moon","Waning Gibbous","Last Quarter","Waning Crescent"}
    assert moon["icon"] in {"🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘"}
    assert 0 <= moon["illumination_pct"] <= 100
    assert 0 <= moon["age_days"] < 29.6
    assert moon["next_full_moon"]
    assert moon["next_new_moon"]
    assert moon["network_access"] is False
    assert moon["additional_ai_calls"] == 0


def test_v08698_environment_exposes_moon_without_network(tmp_path):
    import app as campus
    original = campus.DB_PATH
    campus.DB_PATH = tmp_path / "mavis.db"
    try:
        campus.init_db()
        with campus.db() as conn:
            env = campus.environment_summary(conn)
        assert env["moon"]["phase"]
        assert env["moon"]["network_access"] is False
        assert env["librarian_network_access"] is False
    finally:
        campus.DB_PATH = original


def test_v08698_pond_weather_widget_is_isolated_and_clickable():
    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/world.css").read_text(encoding="utf-8")
    assert 'id="pond-weather-widget"' in index
    assert 'class="pond-living-icons"' in index
    assert "renderPondWeatherWidget()" in js
    assert "env.moon" in js
    assert "pondWeatherWidget?.addEventListener('click',()=>openDrawer('environment'))" in js
    assert ".pond-living-icons{" in css
    assert "z-index:24" in css
    assert f'src="/static/js/app.js?v={LIVE_CACHE_KEY}"' in index
    assert f'href="/static/css/world.css?v={LIVE_CACHE_KEY}"' in index
    assert f'href="/static/css/app.css?v={LIVE_CACHE_KEY}"' in index


def test_v08698_canonical_agent_display_identities(tmp_path, monkeypatch):
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'canonical_agents.db')
    appmod.init_db()
    with appmod.db() as conn:
        rows = {row['id']: dict(row) for row in conn.execute('SELECT id,name,role,home_building_id FROM agents').fetchall()}
    assert rows['chief']['name'] == 'Stella'
    assert rows['chief']['role'] == 'Chief of Staff'
    assert rows['programs']['name'] == 'Percy'
    assert rows['programs']['role'] == 'Director of Programs & Education'
    assert rows['research']['name'] == 'Rose'
    assert rows['research']['role'] == 'Director of Research & Archives'
    assert rows['caretaker']['name'] == 'Stewart'
    assert rows['caretaker']['role'].startswith('Land Steward')
    assert {k: rows[k]['home_building_id'] for k in rows} == {
        'chief':'manor','programs':'barn','research':'library','caretaker':'fruit_forest','operations':'barn','grants':'manor'
    }

def test_v08698_prompt_maps_stable_ids_to_canonical_staff_names():
    prompt = (ROOT / 'prompts/chief_of_staff.txt').read_text(encoding='utf-8')
    assert 'chief — Stella, Chief of Staff' in prompt
    assert 'programs — Percy, Director of Programs & Education' in prompt
    assert 'research — Rose, Director of Research & Archives' in prompt
    assert 'caretaker — Stewart, Land Steward' in prompt
    assert 'chief | research | programs | caretaker' in prompt

def test_v08698_ui_uses_canonical_staff_names_and_new_cache_key():
    index = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    js = (ROOT / 'static/js/app.js').read_text(encoding='utf-8')
    assert LIVE_SHELL_LABEL in index
    assert f'app.js?v={LIVE_CACHE_KEY}' in index
    assert 'Stella · Chief of Staff' in js
    assert 'Percy · Director of Programs & Education' in js
    assert 'Rose · Director of Research & Archives' in js
    assert 'Stewart · Land Steward' in js


def test_v08698_poe_people_and_work_foundation(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe.db')
    appmod.init_db()
    state = appmod.current_state()
    poe = next(a for a in state['agents'] if a['id'] == 'operations')
    assert poe['name'] == 'Poe'
    assert poe['role'] == 'Operations & Volunteer Coordinator'
    assert poe['home_building_id'] == 'barn'
    codes = {c['code'] for c in state['activity_categories']}
    assert {'admin','education','research','farm_land','animal_care','maintenance','grants','outreach','media','planning','learning','volunteer_coordination','other'} <= codes
    created = asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='Sample Volunteer', person_type='Volunteer')))
    with appmod.db() as conn:
        farm_id = int(conn.execute("SELECT id FROM activity_categories WHERE code='farm_land'").fetchone()['id'])
    clocked = asyncio.run(appmod.api_work_clock_in(appmod.WorkClockInRequest(person_id=created['person_id'], activity_category_id=farm_id, participation_type='Volunteer', notes='Garden work')))
    state = appmod.current_state()
    assert state['work_summary']['active_count'] == 1
    assert state['work_sessions'][0]['person_name'] == 'Sample Volunteer'
    assert state['work_sessions'][0]['activity_code'] == 'farm_land'
    result = asyncio.run(appmod.api_work_clock_out(clocked['session_id'], appmod.WorkClockOutRequest()))
    assert result['status'] == 'clocked_out'
    state = appmod.current_state()
    assert state['work_summary']['active_count'] == 0
    actions = [a['action'] for a in state['work_session_audit'] if a['work_session_id'] == clocked['session_id']]
    assert actions[:2] == ['clock_out','clock_in']


def test_v08698_prevents_double_clock_in(tmp_path, monkeypatch):
    import asyncio
    import pytest
    from fastapi import HTTPException
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe-double.db')
    appmod.init_db()
    created = asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='One Timer')))
    with appmod.db() as conn:
        cat = int(conn.execute("SELECT id FROM activity_categories WHERE code='other'").fetchone()['id'])
    req = appmod.WorkClockInRequest(person_id=created['person_id'], activity_category_id=cat)
    asyncio.run(appmod.api_work_clock_in(req))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(appmod.api_work_clock_in(req))
    assert exc.value.status_code == 409


def test_v08698_work_correction_preserves_audit(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe-edit.db')
    appmod.init_db()
    created = asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='Correction Test')))
    with appmod.db() as conn:
        cat = int(conn.execute("SELECT id FROM activity_categories WHERE code='admin'").fetchone()['id'])
    session = asyncio.run(appmod.api_work_clock_in(appmod.WorkClockInRequest(person_id=created['person_id'], activity_category_id=cat)))
    asyncio.run(appmod.api_work_clock_out(session['session_id'], appmod.WorkClockOutRequest()))
    updated = asyncio.run(appmod.api_work_session_edit(session['session_id'], appmod.WorkSessionEditRequest(started_at='2026-09-01T17:00:00+00:00', ended_at='2026-09-01T18:30:00+00:00', notes='Corrected admin session')))
    assert updated['duration_minutes'] == 90
    state = appmod.current_state()
    row = next(x for x in state['work_sessions'] if x['id'] == session['session_id'])
    assert row['duration_minutes'] == 90
    assert row['notes'] == 'Corrected admin session'
    actions = [a['action'] for a in state['work_session_audit'] if a['work_session_id'] == session['session_id']]
    assert actions[:3] == ['edit','clock_out','clock_in']


def test_v08698_people_ui_and_poe_sprite_identity():
    index = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    js = (ROOT / 'static/js/app.js').read_text(encoding='utf-8')
    css = (ROOT / 'static/css/world.css').read_text(encoding='utf-8')
    assert 'data-open-agent="operations"' in index
    assert 'Poe' in index
    assert 'data-person-form' in js
    assert 'data-clock-in-form' in js
    assert 'data-work-clock-out' in js
    assert '/api/work-sessions/clock-in' in js
    assert "operations: '/static/assets/agents/poe-sprite.png'" in (ROOT / 'static/js/world-assets.js').read_text(encoding='utf-8')
    assert '.agent-token.operations .agent-sprite' not in css



def test_v08698_work_report_filters_summarizes_and_groups_monthly(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe-report.db')
    appmod.init_db()
    a = asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='Alex Volunteer')))
    b = asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='Blair Learner')))
    with appmod.db() as conn:
        farm = int(conn.execute("SELECT id FROM activity_categories WHERE code='farm_land'").fetchone()['id'])
        education = int(conn.execute("SELECT id FROM activity_categories WHERE code='education'").fetchone()['id'])
        project = conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES('Fall Garden','Active',?,?)", (appmod.utc_now(),appmod.utc_now()))
        project_id = int(project.lastrowid)
        now = appmod.utc_now()
        conn.execute("INSERT INTO work_sessions(person_id,project_id,activity_category_id,participation_type,started_at,ended_at,duration_minutes,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (a['person_id'],project_id,farm,'Volunteer','2026-09-01T14:00:00+00:00','2026-09-01T16:00:00+00:00',120,'Garden beds','Poe',now,now))
        conn.execute("INSERT INTO work_sessions(person_id,project_id,activity_category_id,participation_type,started_at,ended_at,duration_minutes,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (b['person_id'],None,education,'Learning','2026-08-15T14:00:00+00:00','2026-08-15T15:30:00+00:00',90,'Class','Poe',now,now))
    report = asyncio.run(appmod.api_work_report(start_date='2026-09-01', end_date='2026-09-30'))
    assert report['summary']['minutes'] == 120
    assert report['summary']['hours'] == 2.0
    assert report['summary']['people_count'] == 1
    assert report['by_person'][0]['label'] == 'Alex Volunteer'
    assert report['by_activity'][0]['label'] == 'Farm & Land Stewardship'
    assert report['monthly'][0]['key'] == '2026-09'
    filtered = asyncio.run(appmod.api_work_report(participation_type='Learning'))
    assert filtered['summary']['minutes'] == 90
    assert filtered['by_participation'][0]['label'] == 'Learning'


def test_v08698_work_report_csv_exports_filtered_ledger(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe-csv.db')
    appmod.init_db()
    person = asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='CSV Volunteer')))
    with appmod.db() as conn:
        cat = int(conn.execute("SELECT id FROM activity_categories WHERE code='admin'").fetchone()['id'])
        now = appmod.utc_now()
        conn.execute("INSERT INTO work_sessions(person_id,activity_category_id,participation_type,started_at,ended_at,duration_minutes,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (person['person_id'],cat,'Volunteer','2026-09-02T14:00:00+00:00','2026-09-02T15:00:00+00:00',60,'Records work','Poe',now,now))
    response = asyncio.run(appmod.api_work_report_csv(person_id=person['person_id']))
    body = response.body.decode('utf-8-sig')
    assert response.media_type.startswith('text/csv')
    assert 'CSV Volunteer' in body
    assert 'Records work' in body
    assert 'Administration' in body
    assert 'attachment; filename="mavis-work-hours-' in response.headers['content-disposition']


def test_v08698_work_report_ui_and_cache_key():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    index = (root / 'static' / 'index.html').read_text(encoding='utf-8')
    js = (root / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')
    css = (root / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
    assert LIVE_BUILD in index
    assert f'app.js?v={LIVE_CACHE_KEY}' in index and f'app.css?v={LIVE_CACHE_KEY}' in index and f'world.css?v={LIVE_CACHE_KEY}' in index
    assert 'data-work-report-form' in js
    assert '/api/work-report.csv' in js
    assert 'Monthly Totals' in js
    assert 'work-report-summary' in css



def test_v08698_poe_primary_me_and_clock_commands(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe-talk.db')
    appmod.init_db()
    created = asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='Justyn', is_primary_user=True)))
    with appmod.db() as conn:
        now = appmod.utc_now()
        conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES('Monastic Garden','Active',?,?)", (now, now))
    result = asyncio.run(appmod.api_poe_command(appmod.PoeCommandRequest(text='Poe, clock me in for farm work on the Monastic Garden.')))
    assert result['status'] == 'ok'
    assert result['intent'] == 'clock_in'
    with appmod.db() as conn:
        row = conn.execute("SELECT ws.*,ac.code AS activity_code,p.title AS project_title FROM work_sessions ws LEFT JOIN activity_categories ac ON ac.id=ws.activity_category_id LEFT JOIN projects p ON p.id=ws.project_id WHERE ws.id=?", (result['session_id'],)).fetchone()
        person = conn.execute("SELECT * FROM people WHERE id=?", (created['person_id'],)).fetchone()
    assert person['is_primary_user'] == 1
    assert row['activity_code'] == 'farm_land'
    assert row['project_title'] == 'Monastic Garden'
    assert row['ended_at'] is None
    out = asyncio.run(appmod.api_poe_command(appmod.PoeCommandRequest(text='Poe, clock me out.')))
    assert out['status'] == 'ok'
    assert out['intent'] == 'clock_out'
    with appmod.db() as conn:
        assert conn.execute("SELECT ended_at FROM work_sessions WHERE id=?", (result['session_id'],)).fetchone()['ended_at'] is not None


def test_v08698_poe_manual_duration_is_date_only_and_reportable(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe-manual.db')
    appmod.init_db()
    asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='Sam Helper')))
    result = asyncio.run(appmod.api_poe_command(appmod.PoeCommandRequest(text='Poe, add 2 hours on 2026-08-31 for Sam Helper doing maintenance.')))
    assert result['status'] == 'ok'
    assert result['intent'] == 'manual_duration'
    with appmod.db() as conn:
        row = dict(conn.execute("SELECT * FROM work_sessions WHERE id=?", (result['session_id'],)).fetchone())
        report = appmod.work_report_data(conn, start_date='2026-08-01', end_date='2026-08-31')
    assert row['entry_mode'] == 'manual_duration'
    assert row['work_date'] == '2026-08-31'
    assert row['duration_minutes'] == 120
    assert report['summary']['minutes'] == 120
    assert report['sessions'][0]['local_started_at'] == ''
    assert report['sessions'][0]['local_ended_at'] == ''


def test_v097_poe_past_tense_numeric_date_records_existing_work_session(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe-natural-past.db')
    appmod.init_db()
    person = asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='Justyn')))
    result = asyncio.run(appmod.api_poe_command(appmod.PoeCommandRequest(text='Justyn worked 4 hours on 9.11.26 doing animal care.')))
    assert result['status'] == 'ok'
    assert result['intent'] == 'manual_duration'
    with appmod.db() as conn:
        row = conn.execute("SELECT ws.*,ac.code AS activity_code FROM work_sessions ws JOIN activity_categories ac ON ac.id=ws.activity_category_id WHERE ws.id=?", (result['session_id'],)).fetchone()
    assert row['person_id'] == person['person_id']
    assert row['work_date'] == '2026-09-11'
    assert row['duration_minutes'] == 240
    assert row['entry_mode'] == 'manual_duration'
    assert row['activity_code'] == 'animal_care'


def test_v097_poe_retains_past_work_while_asking_for_category(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe-natural-followup.db')
    appmod.init_db()
    asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='Justyn')))
    first = asyncio.run(appmod.api_poe_command(appmod.PoeCommandRequest(text='Justyn worked 4 hours on 9/11/26.')))
    assert first['status'] == 'clarification'
    assert first['pending_command'] == 'Justyn worked 4 hours on 9/11/26.'
    with appmod.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM work_sessions").fetchone()[0] == 0
    second = asyncio.run(appmod.api_poe_command(appmod.PoeCommandRequest(text='animal care', previous_command=first['pending_command'])))
    assert second['status'] == 'ok'
    with appmod.db() as conn:
        row = conn.execute("SELECT * FROM work_sessions WHERE id=?", (second['session_id'],)).fetchone()
    assert row['work_date'] == '2026-09-11'
    assert row['duration_minutes'] == 240


def test_v097_poe_close_name_requires_confirmation_before_write(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe-name-confirm.db')
    appmod.init_db()
    person = asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='Justyn')))
    first = asyncio.run(appmod.api_poe_command(appmod.PoeCommandRequest(text='Justion worked 4 hours on 9.11.26 doing animal care.')))
    assert first['status'] == 'clarification'
    assert first['suggested_person_id'] == person['person_id']
    assert 'Did you mean Justyn' in first['message']
    with appmod.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM work_sessions").fetchone()[0] == 0
    second = asyncio.run(appmod.api_poe_command(appmod.PoeCommandRequest(text='yes', previous_command=first['pending_command'], suggested_person_id=first['suggested_person_id'])))
    assert second['status'] == 'ok'
    with appmod.db() as conn:
        row = conn.execute("SELECT * FROM work_sessions WHERE id=?", (second['session_id'],)).fetchone()
    assert row['person_id'] == person['person_id']


def test_v097_poe_followup_context_contract_is_present_in_both_interfaces():
    app_text = (ROOT / 'app.py').read_text(encoding='utf-8')
    js = (ROOT / 'static/js/app.js').read_text(encoding='utf-8')
    assert 'previous_command' in app_text
    assert 'previous_poe_command' in app_text
    assert 'poePendingCommand' in js
    assert 'data-poe-clear-pending' in js


def test_v097_ask_campus_keeps_poe_followup_from_routing_to_stewart(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe-campus-followup.db')
    appmod.init_db()
    asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='Justyn')))
    first = asyncio.run(appmod.api_campus_ask(appmod.CampusAskRequest(text='Justyn worked 4 hours on 9/11/26.')))
    assert first['agent'] == 'poe'
    assert first['status'] == 'clarification'
    pending = first['poe_result']['pending_command']
    second = asyncio.run(appmod.api_campus_ask(appmod.CampusAskRequest(
        text='animal care',
        previous_agent='poe',
        previous_poe_command=pending,
    )))
    assert second['agent'] == 'poe'
    assert second['route_source'] == 'follow_up'
    assert second['status'] == 'ok'
    with appmod.db() as conn:
        row = conn.execute("SELECT * FROM work_sessions").fetchone()
    assert row['work_date'] == '2026-09-11'
    assert row['duration_minutes'] == 240


def test_v08698_poe_report_command_uses_primary_and_filters(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe-report-command.db')
    appmod.init_db()
    person = asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='Justyn', is_primary_user=True)))
    with appmod.db() as conn:
        education = int(conn.execute("SELECT id FROM activity_categories WHERE code='education'").fetchone()['id'])
        now = appmod.utc_now()
        conn.execute("INSERT INTO work_sessions(person_id,activity_category_id,participation_type,started_at,ended_at,duration_minutes,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (person['person_id'],education,'Volunteer','2026-08-15T14:00:00+00:00','2026-08-15T15:30:00+00:00',90,'Class prep','Poe',now,now))
    result = asyncio.run(appmod.api_poe_command(appmod.PoeCommandRequest(text='Poe, how many volunteer education hours did I have in August 2026?')))
    assert result['status'] == 'ok'
    assert result['intent'] == 'report'
    assert result['report_summary']['minutes'] == 90
    assert result['report_filters']['person_id'] == person['person_id']
    assert result['report_filters']['participation_type'] == 'Volunteer'
    assert result['report_filters']['start_date'] == '2026-08-01'
    assert result['report_filters']['end_date'] == '2026-08-31'


def test_v08698_poe_refuses_me_without_primary(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe-no-primary.db')
    appmod.init_db()
    asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='Someone Else')))
    result = asyncio.run(appmod.api_poe_command(appmod.PoeCommandRequest(text='Poe, clock me in for admin work.')))
    assert result['status'] == 'clarification'
    assert 'This is me' in result['message']
    with appmod.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM work_sessions").fetchone()[0] == 0


def test_v08698_poe_talk_ui_and_local_parser_contract():
    root = Path(__file__).resolve().parents[1]
    index = (root / 'static' / 'index.html').read_text(encoding='utf-8')
    js = (root / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')
    css = (root / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
    app_text = (root / 'app.py').read_text(encoding='utf-8')
    assert LIVE_BUILD in index
    assert f'app.js?v={LIVE_CACHE_KEY}' in index
    assert 'data-poe-command-form' in js
    assert '/api/poe/command' in js
    assert 'data-person-primary' in js
    assert 'local · no AI call' in js
    assert '.poe-command-card' in css
    assert '@app.post("/api/poe/command")' in app_text
    assert 'manual_duration' in app_text


def test_v08698_additive_upgrade_from_094_people_work_schema(tmp_path, monkeypatch):
    import sqlite3
    import app as appmod
    db_path = tmp_path / 'upgrade-094.db'
    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT NOT NULL,
            person_type TEXT NOT NULL DEFAULT 'Volunteer',
            status TEXT NOT NULL DEFAULT 'Active',
            contact_info TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE work_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL,
            project_id INTEGER,
            activity_category_id INTEGER,
            participation_type TEXT NOT NULL DEFAULT 'Volunteer',
            started_at TEXT NOT NULL,
            ended_at TEXT,
            duration_minutes INTEGER,
            notes TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT 'Poe',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    ''')
    conn.execute("INSERT INTO people(display_name,person_type,status,contact_info,notes,created_at,updated_at) VALUES('Legacy Volunteer','Volunteer','Active','','','2026-08-31T12:00:00+00:00','2026-08-31T12:00:00+00:00')")
    conn.execute("INSERT INTO work_sessions(person_id,participation_type,started_at,ended_at,duration_minutes,notes,created_by,created_at,updated_at) VALUES(1,'Volunteer','2026-08-31T14:00:00+00:00','2026-08-31T15:00:00+00:00',60,'Legacy work','Poe','2026-08-31T15:00:00+00:00','2026-08-31T15:00:00+00:00')")
    conn.commit(); conn.close()

    monkeypatch.setattr(appmod, 'DB_PATH', db_path)
    appmod.init_db()
    with appmod.db() as upgraded:
        people_cols = {row[1] for row in upgraded.execute('PRAGMA table_info(people)').fetchall()}
        work_cols = {row[1] for row in upgraded.execute('PRAGMA table_info(work_sessions)').fetchall()}
        person = upgraded.execute("SELECT display_name,is_primary_user FROM people WHERE id=1").fetchone()
        session = upgraded.execute("SELECT duration_minutes,entry_mode,work_date,notes FROM work_sessions WHERE id=1").fetchone()
    assert 'is_primary_user' in people_cols
    assert {'entry_mode','work_date'}.issubset(work_cols)
    assert person['display_name'] == 'Legacy Volunteer' and person['is_primary_user'] == 0
    assert session['duration_minutes'] == 60 and session['entry_mode'] == 'clock' and session['work_date'] is None


def test_v08698_poe_explicit_name_beats_show_me_filler(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe-name-priority.db')
    appmod.init_db()
    justyn = asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='Justyn', is_primary_user=True)))
    lisa = asyncio.run(appmod.api_person_create(appmod.PersonRequest(display_name='Lisa')))
    with appmod.db() as conn:
        admin = int(conn.execute("SELECT id FROM activity_categories WHERE code='admin'").fetchone()['id'])
        now = appmod.utc_now()
        conn.execute("INSERT INTO work_sessions(person_id,activity_category_id,participation_type,started_at,ended_at,duration_minutes,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (lisa['person_id'],admin,'Volunteer','2026-08-20T14:00:00+00:00','2026-08-20T16:00:00+00:00',120,'Lisa admin','Poe',now,now))
        conn.execute("INSERT INTO work_sessions(person_id,activity_category_id,participation_type,started_at,ended_at,duration_minutes,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (justyn['person_id'],admin,'Volunteer','2026-08-20T14:00:00+00:00','2026-08-20T15:00:00+00:00',60,'Justyn admin','Poe',now,now))
    result = asyncio.run(appmod.api_poe_command(appmod.PoeCommandRequest(text="Poe, show me Lisa's volunteer hours in August 2026.")))
    assert result['status'] == 'ok'
    assert result['report_filters']['person_id'] == lisa['person_id']
    assert result['report_summary']['minutes'] == 120



def test_v08698_grant_desk_schema_agent_and_state(tmp_path, monkeypatch):
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'grant-desk.db')
    appmod.init_db()
    state = appmod.current_state()
    vern = next(a for a in state['agents'] if a['id'] == 'grants')
    assert vern['name'] == 'Vernadette'
    assert vern['role'] == 'Grants & Development Officer'
    assert vern['home_building_id'] == 'manor'
    assert state['grants'] == []
    assert state['grant_summary']['total'] == 0
    with appmod.db() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'grants' in tables
        assert appmod.system_health(conn)['ok'] is True


def test_v08698_grant_create_edit_and_briefing(tmp_path, monkeypatch):
    import asyncio
    from datetime import date, timedelta
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'grant-api.db')
    appmod.init_db()
    campus_today = date.fromisoformat(appmod.current_state()['environment']['local_date'])
    req = appmod.GrantRequest(
        funder='Appalachian Future Fund', title='Community Food Education', deadline=(campus_today + timedelta(days=7)).isoformat(),
        amount_min=10000, amount_max=25000, status='Pursue', mission_fit=5, workload=3,
        restrictions=2, strategic_value=5, recommendation='Pursue', assessment_notes='Strong fit.'
    )
    created = asyncio.run(appmod.api_grant_create(req))
    assert created['status'] == 'created'
    state = appmod.current_state()
    grant = state['grants'][0]
    assert grant['funder'] == 'Appalachian Future Fund'
    assert grant['recommendation'] == 'Pursue'
    assert state['grant_summary']['upcoming_30_days'] == 1
    priorities = [p for p in state['executive_briefing']['priorities'] if p.get('kind') == 'grant_deadline']
    assert priorities and priorities[0]['grant_id'] == created['grant_id']
    edited_req = req.model_copy(update={'status':'Preparing','assessment_notes':'Draft underway.'})
    edited = asyncio.run(appmod.api_grant_edit(created['grant_id'], edited_req))
    assert edited['status'] == 'updated'
    assert appmod.current_state()['grants'][0]['status'] == 'Preparing'


def test_v08698_grant_reset_survival(tmp_path, monkeypatch):
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'grant-reset.db')
    appmod.init_db()
    with appmod.db() as conn:
        now=appmod.utc_now()
        project_id=int(conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES('Farm Project','Active',?,?)",(now,now)).lastrowid)
        conn.execute("INSERT INTO grants(funder,title,deadline,status,project_id,mission_fit,workload,restrictions,strategic_value,recommendation,created_at,updated_at) VALUES('Funder','Grant','2026-09-20','Reviewing',?,4,2,2,4,'Review',?,?)",(project_id,now,now))
    appmod.reset_runtime()
    with appmod.db() as conn:
        row=conn.execute("SELECT title,project_id FROM grants").fetchone()
        assert row['title'] == 'Grant'
        assert row['project_id'] is None


def test_v08698_grant_ui_and_cache_key():
    index=(ROOT/'static/index.html').read_text(encoding='utf-8')
    js=(ROOT/'static/js/app.js').read_text(encoding='utf-8')
    css=(ROOT/'static/css/app.css').read_text(encoding='utf-8')
    world=(ROOT/'static/css/world.css').read_text(encoding='utf-8')
    assert LIVE_BUILD in index
    assert f'app.js?v={LIVE_CACHE_KEY}' in index and f'app.css?v={LIVE_CACHE_KEY}' in index
    assert 'data-panel="grants"' in index
    assert 'function drawerGrants()' in js
    assert 'data-grant-form' in js
    assert '/api/grants' in js
    assert '.vernadette-callout' in css
    assert "grants: '/static/assets/agents/vernadette-sprite.png'" in (ROOT / 'static/js/world-assets.js').read_text(encoding='utf-8')
    assert '.agent-token.grants .agent-sprite' not in world



def test_v08698_vernadette_add_report_update_commands(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'vernadette-talk.db')
    appmod.init_db()
    added = asyncio.run(appmod.api_vernadette_command(appmod.VernadetteCommandRequest(
        text='Vernadette, add a grant from Appalachian Future Fund called Community Food Education due September 30, 2026 for $25,000.'
    )))
    assert added['status'] == 'ok' and added['action'] == 'add'
    assert added['grants'][0]['title'] == 'Community Food Education'
    assert added['grants'][0]['deadline'] == '2026-09-30'
    assert added['grants'][0]['amount_min'] == 25000
    assert added['grants'][0]['amount_max'] == 25000

    due = asyncio.run(appmod.api_vernadette_command(appmod.VernadetteCommandRequest(text='Vernadette, what grants are due this month?')))
    assert due['status'] == 'ok'
    assert [g['title'] for g in due['grants']] == ['Community Food Education']

    moved = asyncio.run(appmod.api_vernadette_command(appmod.VernadetteCommandRequest(text='Vernadette, mark Community Food Education as Preparing.')))
    assert moved['status'] == 'ok'
    assert moved['grants'][0]['status'] == 'Preparing'

    recommended = asyncio.run(appmod.api_vernadette_command(appmod.VernadetteCommandRequest(text='Vernadette, set Community Food Education recommendation to Pursue.')))
    assert recommended['status'] == 'ok'
    assert recommended['grants'][0]['recommendation'] == 'Pursue'

    pursue = asyncio.run(appmod.api_vernadette_command(appmod.VernadetteCommandRequest(text='Vernadette, what should we pursue?')))
    assert pursue['status'] == 'ok'
    assert [g['title'] for g in pursue['grants']] == ['Community Food Education']


def test_v08698_vernadette_next_deadline_and_ambiguity(tmp_path, monkeypatch):
    import asyncio
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'vernadette-deadlines.db')
    appmod.init_db()
    with appmod.db() as conn:
        now=appmod.utc_now()
        today=appmod._vernadette_local_today(conn)
        first=(today+appmod.timedelta(days=1)).isoformat()
        second=(today+appmod.timedelta(days=8)).isoformat()
        conn.execute("INSERT INTO grants(funder,title,deadline,status,mission_fit,workload,restrictions,strategic_value,recommendation,created_at,updated_at) VALUES('One Fund','Garden One',?,'Reviewing',3,3,3,3,'Review',?,?)",(first,now,now))
        conn.execute("INSERT INTO grants(funder,title,deadline,status,mission_fit,workload,restrictions,strategic_value,recommendation,created_at,updated_at) VALUES('Two Fund','Garden Two',?,'Pursue',3,3,3,3,'Pursue',?,?)",(second,now,now))
    next_one = asyncio.run(appmod.api_vernadette_command(appmod.VernadetteCommandRequest(text='Vernadette, what is the next grant deadline?')))
    assert next_one['status'] == 'ok'
    assert next_one['grants'][0]['title'] == 'Garden One'
    ambiguous = asyncio.run(appmod.api_vernadette_command(appmod.VernadetteCommandRequest(text='Vernadette, mark Garden as Submitted.')))
    assert ambiguous['status'] == 'clarification'


def test_v08698_vernadette_conversation_ui_contract():
    index=(ROOT/'static/index.html').read_text(encoding='utf-8')
    js=(ROOT/'static/js/app.js').read_text(encoding='utf-8')
    css=(ROOT/'static/css/app.css').read_text(encoding='utf-8')
    app_text=(ROOT/'app.py').read_text(encoding='utf-8')
    assert LIVE_BUILD in index
    assert f'app.js?v={LIVE_CACHE_KEY}' in index and f'app.css?v={LIVE_CACHE_KEY}' in index
    assert 'data-vernadette-command-form' in js
    assert '/api/vernadette/command' in js
    assert 'local + federal search · no AI call' in js
    assert '.vernadette-command-card' in css
    assert '.grant-discovery-panel' in css
    assert '@app.post("/api/vernadette/command")' in app_text
    assert '@app.post("/api/grants/discover")' in app_text
    assert 'Search Grants.gov' in js


def test_v086981_poe_home_is_coopenheimer_barn_on_upgrade(tmp_path, monkeypatch):
    import app as appmod
    monkeypatch.setattr(appmod, 'DB_PATH', tmp_path / 'poe-home-upgrade.db')
    appmod.init_db()
    with appmod.db() as conn:
        conn.execute("UPDATE agents SET home_building_id='manor', building_id='manor', task_id=NULL WHERE id='operations'")
    appmod.init_db()
    with appmod.db() as conn:
        poe = conn.execute("SELECT home_building_id, building_id FROM agents WHERE id='operations'").fetchone()
        assert poe['home_building_id'] == 'barn'
        assert poe['building_id'] == 'barn'


def test_v08698_grants_gov_provider_normalizes_search(monkeypatch):
    import json
    import grant_provider

    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({
                "errorcode": 0,
                "msg": "Webservice Succeeds",
                "data": {
                    "hitCount": 2,
                    "oppHits": [
                        {"id": "363000", "number": "USDA-TEST-1", "title": "Rural Food Education", "agencyCode": "USDA", "agencyName": "Department of Agriculture", "openDate": "08/20/2026", "closeDate": "10/15/2026", "oppStatus": "posted", "docType": "synopsis", "alnist": ["10.500"]},
                        {"id": "363001", "number": "EPA-TEST-2", "title": "Community Water Learning", "agencyCode": "EPA", "agencyName": "Environmental Protection Agency", "openDate": "", "closeDate": "", "oppStatus": "forecasted", "docType": "forecast", "alnist": []},
                    ],
                },
            }).encode()

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(grant_provider, "urlopen", fake_urlopen)
    result = grant_provider.search_grants_gov("rural education", rows=10)
    assert captured["url"] == "https://api.grants.gov/v1/api/search2"
    assert captured["body"]["oppStatuses"] == "posted|forecasted"
    assert captured["body"]["keyword"] == "rural education"
    assert result["hit_count"] == 2
    assert result["results"][0]["source_key"] == "363000"
    assert result["results"][0]["deadline"] == "2026-10-15"
    assert result["results"][0]["source_url"].endswith("/363000")
    assert result["results"][1]["source_status"] == "forecasted"


def test_v08698_grant_discovery_import_is_review_first_and_deduplicated(tmp_path, monkeypatch):
    import asyncio
    import app as appmod

    monkeypatch.setattr(appmod, "DB_PATH", tmp_path / "grant-discovery.db")
    appmod.init_db()

    def fake_search(keyword, rows=20):
        assert keyword == "rural community education"
        return {
            "provider": "Grants.gov", "query": keyword, "hit_count": 1, "returned": 1,
            "results": [{
                "source_name": "Grants.gov", "source_key": "363100", "opportunity_number": "USDA-RURAL-1",
                "title": "Rural Community Education", "funder": "Department of Agriculture", "agency_code": "USDA",
                "open_date": "2026-08-20", "deadline": "2026-10-10", "source_status": "posted", "document_type": "synopsis",
                "alns": ["10.500"], "source_url": "https://www.grants.gov/search-results-detail/363100",
            }],
        }

    monkeypatch.setattr(appmod, "search_grants_gov", fake_search)
    discovered = asyncio.run(appmod.api_grant_discover(appmod.GrantDiscoveryRequest(keyword="rural community education")))
    assert discovered["returned"] == 1
    assert discovered["results"][0]["already_in_desk"] is False

    imported = asyncio.run(appmod.api_grant_import_discovery(appmod.GrantDiscoveryImportRequest(
        source_key="363100", opportunity_number="USDA-RURAL-1", title="Rural Community Education",
        funder="Department of Agriculture", deadline="2026-10-10", source_status="posted"
    )))
    assert imported["status"] == "created"
    grant = appmod.current_state()["grants"][0]
    assert grant["source_name"] == "Grants.gov"
    assert grant["source_key"] == "363100"
    assert grant["status"] == "Discovered"
    assert grant["recommendation"] == "Review"
    assert grant["mission_fit"] == grant["workload"] == grant["restrictions"] == grant["strategic_value"] == 3

    second = asyncio.run(appmod.api_grant_import_discovery(appmod.GrantDiscoveryImportRequest(
        source_key="363100", opportunity_number="USDA-RURAL-1", title="Rural Community Education",
        funder="Department of Agriculture", deadline="2026-10-10", source_status="posted"
    )))
    assert second["status"] == "already_exists"
    assert len(appmod.current_state()["grants"]) == 1

    discovered_again = asyncio.run(appmod.api_grant_discover(appmod.GrantDiscoveryRequest(keyword="rural community education")))
    assert discovered_again["results"][0]["already_in_desk"] is True
    assert discovered_again["results"][0]["grant_id"] == imported["grant_id"]


def test_v08698_vernadette_natural_command_can_discover_federal_grants(tmp_path, monkeypatch):
    import asyncio
    import app as appmod

    monkeypatch.setattr(appmod, "DB_PATH", tmp_path / "vernadette-discovery.db")
    appmod.init_db()

    def fake_search(keyword, rows=20):
        assert keyword == "conservation water"
        return {"provider": "Grants.gov", "query": keyword, "hit_count": 1, "returned": 1, "results": [{
            "source_name": "Grants.gov", "source_key": "363200", "opportunity_number": "EPA-WATER-1", "title": "Water Conservation Education",
            "funder": "Environmental Protection Agency", "agency_code": "EPA", "open_date": "2026-09-01", "deadline": "2026-11-01",
            "source_status": "forecasted", "document_type": "forecast", "alns": [], "source_url": "https://www.grants.gov/search-results-detail/363200"
        }]}

    monkeypatch.setattr(appmod, "search_grants_gov", fake_search)
    result = asyncio.run(appmod.api_vernadette_command(appmod.VernadetteCommandRequest(text="Vernadette, find grants for conservation water.")))
    assert result["status"] == "ok"
    assert result["action"] == "discover"
    assert result["query"] == "conservation water"
    assert result["discovery_results"][0]["title"] == "Water Conservation Education"
    assert result["discovery_results"][0]["already_in_desk"] is False


def test_v08698_grant_discovery_schema_additive_upgrade(tmp_path, monkeypatch):
    import sqlite3
    import app as appmod

    db_path = tmp_path / "grant-upgrade.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE grants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            funder TEXT NOT NULL,
            title TEXT NOT NULL,
            deadline TEXT,
            amount_min REAL,
            amount_max REAL,
            amount_notes TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Discovered',
            project_id INTEGER,
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
        INSERT INTO grants(funder,title,status,created_at,updated_at) VALUES('Old Funder','Existing Grant','Reviewing','2026-09-01','2026-09-01');
    """)
    conn.commit()
    conn.close()

    monkeypatch.setattr(appmod, "DB_PATH", db_path)
    appmod.init_db()
    with appmod.db() as c:
        columns = {r[1] for r in c.execute("PRAGMA table_info(grants)").fetchall()}
        assert {"source_name", "source_key", "opportunity_number", "source_status"} <= columns
        row = c.execute("SELECT title,status,source_name,source_key FROM grants WHERE title='Existing Grant'").fetchone()
        assert row["status"] == "Reviewing"
        assert row["source_name"] == "" and row["source_key"] == ""


def test_v08698_grant_discovery_ui_contract():
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/app.css").read_text(encoding="utf-8")
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "data-grant-discovery-form" in js
    assert "data-grant-import-source" in js
    assert "/api/grants/discover" in js
    assert "/api/grants/import-discovery" in js
    assert "Search Grants.gov" in js
    assert ".grant-discovery-panel" in css
    assert "source_key TEXT NOT NULL" in app_text
    assert "search_grants_gov" in app_text
    assert "This release searches **Grants.gov only**" in readme


def test_v086981_weather_key_reads_campus_env_mapping(monkeypatch):
    import weather_provider as wp
    monkeypatch.setattr(wp, "combined_environment", lambda: {"WEATHER_UNDERGROUND_API_KEY": "pws-secret"})
    assert wp.weather_underground_key_available() is True
    assert wp._api_key() == "pws-secret"


def test_v086981_weather_fetch_retries_transient_timeout(monkeypatch):
    import io
    import socket
    import weather_provider as wp

    calls = {"count": 0}

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def read(self, limit): return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise socket.timeout("temporary read timeout")
        return FakeResponse()

    monkeypatch.setattr(wp, "urlopen", fake_urlopen)
    monkeypatch.setattr(wp.time, "sleep", lambda _: None)
    result = wp.fetch_json("https://api.open-meteo.com/v1/forecast", {"latitude": 1}, timeout=0.1, attempts=2)
    assert result == {"ok": True}
    assert calls["count"] == 2


def test_v0869811_weather_status_distinguishes_pws_auth_failure_from_forecast(tmp_path, monkeypatch):
    import app as campus
    original = campus.DB_PATH
    campus.DB_PATH = tmp_path / "mavis.db"
    monkeypatch.setenv("WEATHER_UNDERGROUND_API_KEY", "configured-test-key")
    try:
        campus.init_db()
        today = campus.datetime.now(campus.timezone.utc).date().isoformat()
        with campus.db() as conn:
            conn.execute(
                "UPDATE environment_settings SET last_refresh_at=?, last_refresh_status=?, last_refresh_error=? WHERE id=1",
                (campus.utc_now(), "Forecast fallback", "PWS: HTTP Error 401: Unauthorized"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO weather_daily(forecast_date,summary,source,updated_at) VALUES(?,?,?,?)",
                (today, "Regional forecast", "Open-Meteo", campus.utc_now()),
            )
            env = campus.environment_summary(conn)
        assert env["pws_api_key_configured"] is True
        assert env["pws_connection_status"] == "Authorization failed"
        assert "rejected" in env["pws_status_detail"].lower()
        assert env["forecast_connection_status"] == "Connected"
    finally:
        campus.DB_PATH = original



def test_v087_daily_steward_caps_focus_and_prioritizes_human_gate(tmp_path, monkeypatch):
    import app as campus
    original = campus.DB_PATH
    campus.DB_PATH = tmp_path / "daily-steward.db"
    try:
        campus.init_db()
        now = campus.utc_now()
        with campus.db() as conn:
            pid = int(conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)", ("Autumn Class", "Awaiting Approval", now, now)).lastrowid)
            conn.execute("INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (pid,"Prepare worksheet","programs","Waiting",1,"",now,now))
            conn.execute("INSERT INTO approvals(project_id,title,summary,status,created_at,updated_at) VALUES(?,?,?,?,?,?)", (pid,"Approve Autumn Class plan","Ready for review","Pending",now,now))
            steward = campus.daily_steward(conn)
        assert steward["additional_ai_calls"] == 0
        assert len(steward["focus"]) <= 3
        assert steward["focus"][0]["kind"] == "decision"
        assert steward["focus"][0]["agent"] == "Stella"
        assert "new major project" in steward["protect_attention"].lower()
        assert steward["calendar"]["connected"] is True
    finally:
        campus.DB_PATH = original


def test_v087_daily_steward_weather_adjusts_recorded_land_task_without_inventing_one(tmp_path, monkeypatch):
    import app as campus
    original = campus.DB_PATH
    campus.DB_PATH = tmp_path / "daily-weather.db"
    try:
        campus.init_db()
        with campus.db() as conn:
            today = campus.environment_summary(conn)["local_date"]
            tomorrow = (campus.date.fromisoformat(today) + campus.timedelta(days=1)).isoformat()
            conn.execute("INSERT OR REPLACE INTO weather_daily(forecast_date,high_f,low_f,precip_chance,summary,source,updated_at) VALUES(?,?,?,?,?,?,?)", (today,72,50,10,"Dry","Open-Meteo",campus.utc_now()))
            conn.execute("INSERT OR REPLACE INTO weather_daily(forecast_date,high_f,low_f,precip_chance,summary,source,updated_at) VALUES(?,?,?,?,?,?,?)", (tomorrow,68,51,80,"Rain","Open-Meteo",campus.utc_now()))
            now=campus.utc_now()
            pid=int(conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)", ("Fruit Forest Care","Active",now,now)).lastrowid)
            conn.execute("INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (pid,"Mulch young trees","caretaker","Waiting",1,"",now,now))
            steward=campus.daily_steward(conn)
        assert any(x["title"]=="Mulch young trees" for x in steward["focus"])
        item=next(x for x in steward["focus"] if x["title"]=="Mulch young trees")
        assert "forecast" in item["why"].lower()
        assert any("dry-work window" in x["detail"].lower() for x in steward["watch"])
    finally:
        campus.DB_PATH=original


def test_v087_stella_daily_endpoint_is_local_and_bounded(tmp_path, monkeypatch):
    import asyncio
    import app as campus
    original=campus.DB_PATH
    campus.DB_PATH=tmp_path/'stella-daily.db'
    try:
        campus.init_db()
        result=asyncio.run(campus.api_stella_daily(campus.StellaDailyRequest(text='Stella, what should I focus on today?')))
        assert result['status']=='ok'
        assert result['additional_ai_calls']==0
        assert len(result['daily_steward']['focus'])<=3
        clarification=asyncio.run(campus.api_stella_daily(campus.StellaDailyRequest(text='Tell me a joke.')))
        assert clarification['status']=='clarification'
    finally:
        campus.DB_PATH=original


def test_v087_daily_steward_ui_manifest_and_cache_key():
    import json
    index=(ROOT/'static/index.html').read_text(encoding='utf-8')
    js=(ROOT/'static/js/app.js').read_text(encoding='utf-8')
    css=(ROOT/'static/css/app.css').read_text(encoding='utf-8')
    data=json.loads((ROOT/'static/assets/asset-manifest.json').read_text(encoding='utf-8'))
    assert LIVE_SHELL_LABEL in index
    assert 'Stella Daily Steward' in index
    assert 'data-stella-daily-form' in js and '/api/stella/daily' in js
    assert 'What to focus on today' in js and 'Protect your attention' in js
    assert '.daily-focus-card' in css
    assert f'app.js?v={LIVE_CACHE_KEY}' in index and f'app.css?v={LIVE_CACHE_KEY}' in index and f'world.css?v={LIVE_CACHE_KEY}' in index
    assert data['daily_steward']['enabled'] is True
    assert data['daily_steward']['max_focus_items']==3
    assert data['daily_steward']['calendar_connected'] is True



def test_v08742_calendar_schema_state_and_api(tmp_path, monkeypatch):
    import asyncio
    import app as campus
    original=campus.DB_PATH
    campus.DB_PATH=tmp_path/'calendar.db'
    try:
        campus.init_db()
        created=asyncio.run(campus.api_event_create(campus.EventRequest(
            title='Save Your Documents class', event_date=campus.environment_summary(campus.db().__enter__())['local_date'] if False else '2026-09-01',
            start_time='18:00', end_time='19:00', location='Craft Memorial Library', event_type='Class / Program', commitment_level='Major'
        )))
        assert created['status']=='created'
        state=campus.current_state()
        assert len(state['events'])==1
        event=state['events'][0]
        assert event['title']=='Save Your Documents class'
        assert event['commitment_level']=='Major'
        assert state['calendar_summary']['enabled'] is True
        tables=set()
        with campus.db() as conn:
            tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'events' in tables
    finally:
        campus.DB_PATH=original


def test_v08742_calendar_major_commitment_reduces_stella_focus(tmp_path, monkeypatch):
    import app as campus
    original=campus.DB_PATH
    campus.DB_PATH=tmp_path/'calendar-stella.db'
    try:
        campus.init_db()
        with campus.db() as conn:
            today=campus.environment_summary(conn)['local_date']
            now=campus.utc_now()
            conn.execute("INSERT INTO events(title,event_date,start_time,end_time,all_day,location,event_type,commitment_level,notes,status,created_by,created_at,updated_at) VALUES(?,?,?,?,0,?,?,?,?,?,'Human',?,?)",
                         ('Library class',today,'18:00','19:00','Library','Class / Program','Major','','Scheduled',now,now))
            for i,owner in enumerate(['programs','caretaker','research'],1):
                pid=int(conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",(f'Project {i}','Active',now,now)).lastrowid)
                conn.execute("INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(pid,f'Task {i}',owner,'Waiting',1,'',now,now))
            steward=campus.daily_steward(conn)
        assert steward['calendar']['connected'] is True
        assert steward['calendar_pressure']['major_today_count']==1
        assert steward['focus_cap']==2
        assert len(steward['focus'])<=2
        assert 'calendar' in steward['protect_attention'].lower()
        assert any(x['source']=='Calendar' for x in steward['watch'])
    finally:
        campus.DB_PATH=original


def test_daily_steward_linked_commitment_supports_existing_project_task(tmp_path, monkeypatch):
    import app as campus
    original = campus.DB_PATH
    campus.DB_PATH = tmp_path / "linked-commitment.db"
    try:
        campus.init_db()
        with campus.db() as conn:
            today = campus.date.fromisoformat(campus.environment_summary(conn)["local_date"])
            event_date = (today + campus.timedelta(days=2)).isoformat()
            now = campus.utc_now()
            linked_project = int(conn.execute(
                "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                ("Library Class", "Active", now, now),
            ).lastrowid)
            other_project = int(conn.execute(
                "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                ("Other Program", "Active", now, now),
            ).lastrowid)
            conn.execute(
                "INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (linked_project, "Review class handout", "research", "Waiting", 1, "", now, now),
            )
            conn.execute(
                "INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (other_project, "Plan another workshop", "programs", "Waiting", 1, "", now, now),
            )
            event_id = int(conn.execute(
                "INSERT INTO events(title,event_date,all_day,location,event_type,commitment_level,project_id,notes,status,created_by,created_at,updated_at) VALUES(?,?,1,?,?,?,?,?,?,?,?,?)",
                ("Digital Preservation at the Library", event_date, "Library", "Class / Program", "Normal", linked_project, "", "Scheduled", "Human", now, now),
            ).lastrowid)
            before = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("projects", "tasks", "events")}
            steward = campus.daily_steward(conn)
            after = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in before}
        assert steward["focus"][0]["title"] == "Review class handout"
        assert steward["focus"][0]["commitment_event_id"] == event_id
        assert steward["focus"][0]["commitment_event_date"] == event_date
        assert "Digital Preservation at the Library" in steward["focus"][0]["why"]
        assert event_date in steward["focus"][0]["why"]
        assert "specific purpose is not assumed" in steward["focus"][0]["why"]
        assert before == after
    finally:
        campus.DB_PATH = original


def test_daily_steward_ignores_unlinked_inactive_and_distant_events(tmp_path, monkeypatch):
    import app as campus
    original = campus.DB_PATH
    campus.DB_PATH = tmp_path / "ineligible-commitments.db"
    try:
        campus.init_db()
        with campus.db() as conn:
            today = campus.date.fromisoformat(campus.environment_summary(conn)["local_date"])
            now = campus.utc_now()
            projects = []
            for index, owner in enumerate(("research", "research", "research", "programs"), 1):
                project_id = int(conn.execute(
                    "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                    (f"Project {index}", "Active", now, now),
                ).lastrowid)
                projects.append(project_id)
                conn.execute(
                    "INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (project_id, f"Task {index}", owner, "Waiting", 1, "", now, now),
                )
            non_active_project = int(conn.execute(
                "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                ("Awaiting Library Decision", "Awaiting Library Decision", now, now),
            ).lastrowid)
            conn.execute(
                "INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (non_active_project, "Task 5", "research", "In Progress", 1, "", now, now),
            )
            events = [
                ("Unlinked class", 2, None, "Scheduled"),
                ("Cancelled class", 2, projects[1], "Cancelled"),
                ("Distant class", campus.DAILY_STEWARD_COMMITMENT_LOOKAHEAD_DAYS + 1, projects[2], "Scheduled"),
                ("Non-active project class", 1, non_active_project, "Scheduled"),
            ]
            for title, days, project_id, status in events:
                conn.execute(
                    "INSERT INTO events(title,event_date,all_day,location,event_type,commitment_level,project_id,notes,status,created_by,created_at,updated_at) VALUES(?,?,1,?,?,?,?,?,?,?,?,?)",
                    (title, (today + campus.timedelta(days=days)).isoformat(), "Library", "Class / Program", "Normal", project_id, "", status, "Human", now, now),
                )
            steward = campus.daily_steward(conn)
        assert steward["focus"][0]["title"] == "Task 5"
        assert all("commitment_event_id" not in item for item in steward["focus"])
        assert campus.DAILY_STEWARD_COMMITMENT_LOOKAHEAD_DAYS == 14
    finally:
        campus.DB_PATH = original


def test_daily_steward_human_gate_outranks_linked_commitment(tmp_path, monkeypatch):
    import app as campus
    original = campus.DB_PATH
    campus.DB_PATH = tmp_path / "commitment-precedence.db"
    try:
        campus.init_db()
        with campus.db() as conn:
            today = campus.date.fromisoformat(campus.environment_summary(conn)["local_date"])
            now = campus.utc_now()
            project_id = int(conn.execute(
                "INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)",
                ("Library Class", "Active", now, now),
            ).lastrowid)
            conn.execute(
                "INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (project_id, "Assemble class materials", "programs", "Waiting", 1, "", now, now),
            )
            conn.execute(
                "INSERT INTO events(title,event_date,all_day,location,event_type,commitment_level,project_id,notes,status,created_by,created_at,updated_at) VALUES(?,?,1,?,?,?,?,?,?,?,?,?)",
                ("Library class", (today + campus.timedelta(days=1)).isoformat(), "Library", "Class / Program", "Normal", project_id, "", "Scheduled", "Human", now, now),
            )
            conn.execute(
                "INSERT INTO approvals(project_id,title,summary,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (project_id, "Approve class plan", "Ready", "Pending", now, now),
            )
            steward = campus.daily_steward(conn)
        assert steward["focus"][0]["kind"] == "decision"
        assert steward["focus"][0]["title"] == "Approve class plan"
        assert len(steward["focus"]) <= 3
    finally:
        campus.DB_PATH = original


def test_v08742_calendar_ui_manifest_and_cache_key():
    import json
    index=(ROOT/'static/index.html').read_text(encoding='utf-8')
    js=(ROOT/'static/js/app.js').read_text(encoding='utf-8')
    css=(ROOT/'static/css/app.css').read_text(encoding='utf-8')
    data=json.loads((ROOT/'static/assets/asset-manifest.json').read_text(encoding='utf-8'))
    assert LIVE_SHELL_LABEL in index
    assert 'data-panel="calendar"' in index
    assert 'function drawerCalendar()' in js
    assert 'data-calendar-event-form' in js and '/api/events' in js
    assert '.calendar-event-card' in css
    assert f'app.js?v={LIVE_CACHE_KEY}' in index and f'app.css?v={LIVE_CACHE_KEY}' in index and f'world.css?v={LIVE_CACHE_KEY}' in index
    assert data['calendar_foundation']['enabled'] is True
    assert data['daily_steward']['calendar_connected'] is True
    assert data['calendar_foundation']['google_calendar_connected'] is True


def test_google_calendar_v1_refresh_uses_existing_events_and_preserves_annotations(tmp_path, monkeypatch):
    import app as campus
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "google-calendar.db")
    campus.init_db()
    raw = [{
        "id": "google-instance-1", "status": "confirmed", "summary": "Board meeting",
        "start": {"dateTime": "2026-09-20T14:00:00-04:00"},
        "end": {"dateTime": "2026-09-20T15:00:00-04:00"},
        "location": "Mavis Manor", "updated": "2026-09-14T12:00:00Z",
        "attendees": [{"email": "private@example.com"}], "description": "private detail",
    }]
    tz = campus.ZoneInfo("America/New_York")
    with campus.db() as conn:
        assert campus._store_google_calendar_refresh(conn, raw, window_start=campus.date(2026, 8, 15), window_end=campus.date(2027, 3, 15), tz=tz) == 1
        row = conn.execute("SELECT * FROM events WHERE external_event_id='google-instance-1'").fetchone()
        assert row["source"] == "google_calendar" and row["event_date"] == "2026-09-20" and row["start_time"] == "14:00"
        assert "attendee" not in row.keys() and "description" not in row.keys()
        conn.execute("UPDATE events SET event_type='Meeting',commitment_level='Major',notes='Bring local agenda' WHERE id=?", (row["id"],))
        changed = [{**raw[0], "summary": "Board meeting revised", "location": "Library of Mavis"}]
        campus._store_google_calendar_refresh(conn, changed, window_start=campus.date(2026, 8, 15), window_end=campus.date(2027, 3, 15), tz=tz)
        row = conn.execute("SELECT * FROM events WHERE id=?", (row["id"],)).fetchone()
        assert (row["title"], row["location"]) == ("Board meeting revised", "Library of Mavis")
        assert (row["event_type"], row["commitment_level"], row["notes"]) == ("Meeting", "Major", "Bring local agenda")
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        campus._store_google_calendar_refresh(conn, [], window_start=campus.date(2026, 8, 15), window_end=campus.date(2027, 3, 15), tz=tz)
        assert conn.execute("SELECT status FROM events WHERE id=?", (row["id"],)).fetchone()[0] == "Cancelled"


def test_google_calendar_v1_google_owned_fields_are_backend_read_only(tmp_path, monkeypatch):
    import asyncio
    import app as campus
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "google-owned.db")
    campus.init_db()
    now = campus.utc_now()
    with campus.db() as conn:
        event_id = conn.execute("""INSERT INTO events(title,event_date,start_time,end_time,all_day,location,event_type,commitment_level,notes,status,created_by,created_at,updated_at,source,external_calendar_id,external_event_id)
            VALUES('Google title','2026-09-20','10:00','11:00',0,'Google place','Personal','Normal','','Scheduled','Google Calendar',?,?,'google_calendar','primary','g1')""", (now, now)).lastrowid
    asyncio.run(campus.api_event_edit(event_id, campus.EventRequest(title="Tampered", event_date="2027-01-01", start_time="01:00", end_time="02:00", location="Tampered", status="Cancelled", event_type="Farm", commitment_level="Major", notes="Local", project_id=None)))
    with campus.db() as conn:
        row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    assert (row["title"],row["event_date"],row["start_time"],row["location"],row["status"]) == ("Google title","2026-09-20","10:00","Google place","Scheduled")
    assert (row["event_type"],row["commitment_level"],row["notes"]) == ("Farm","Major","Local")


def test_google_calendar_v1_token_boundary_and_ui_contract(tmp_path, monkeypatch):
    import google_calendar_provider as provider
    monkeypatch.setattr(provider, "combined_environment", lambda: {"GOOGLE_CALENDAR_CLIENT_ID":"client-id","GOOGLE_CALENDAR_CLIENT_SECRET":"client-secret"})
    monkeypatch.setattr(provider, "_post_form", lambda url, values, timeout=20: {"refresh_token":"refresh-secret","access_token":"access-secret","expires_in":3600})
    url = provider.begin_authorization("http://127.0.0.1:8000/api/calendar/google/callback")
    from urllib.parse import parse_qs, urlparse
    state = parse_qs(urlparse(url).query)["state"][0]
    provider.complete_authorization(tmp_path, state=state, code="code", redirect_uri="http://127.0.0.1:8000/api/calendar/google/callback")
    token = tmp_path / provider.TOKEN_FILENAME
    assert token.is_file() and "refresh-secret" in token.read_text(encoding="utf-8")
    provider.disconnect(tmp_path)
    assert not token.exists()
    js=(ROOT/'static/js/app.js').read_text(encoding='utf-8')
    ignore=(ROOT/'.gitignore').read_text(encoding='utf-8')
    helper=(ROOT/'upgrade_helper.py').read_text(encoding='utf-8')
    assert all(x in js for x in ('data-google-calendar-connect','data-google-calendar-refresh','data-google-calendar-disconnect','Google Calendar ·'))
    assert provider.TOKEN_FILENAME in ignore and provider.TOKEN_FILENAME in helper


def test_v08742_cleanup_people_first_ui_and_stable_ids():
    import json
    index=(ROOT/'static/index.html').read_text(encoding='utf-8')
    js=(ROOT/'static/js/app.js').read_text(encoding='utf-8')
    data=json.loads((ROOT/'static/assets/asset-manifest.json').read_text(encoding='utf-8'))
    assert 'Campus Team' in index
    for name in ['Stella','Percy','Rose','Stewart','Vernadette','Poe']:
        assert f'<strong>{name}</strong>' in index
    assert 'ASK THE CAMPUS' in index and 'id="campus-agent"' in index
    assert 'Nothing becomes a project unless you explicitly choose to create one.' in index
    assert "programs:{x:-4.2,y:0.9}" in js
    assert "operations:{x:4.6,y:3.2}" in js
    assert data['campus_cleanup']['internal_agent_ids_preserved'] is True


def test_v08742_compact_weather_moon_icons_replace_map_card():
    index=(ROOT/'static/index.html').read_text(encoding='utf-8')
    js=(ROOT/'static/js/app.js').read_text(encoding='utf-8')
    css=(ROOT/'static/css/world.css').read_text(encoding='utf-8')
    assert 'class="pond-living-icons"' in index
    assert 'class="living-weather-card kind-cloud"' in index
    assert 'class="living-moon-chip"' in index
    assert '.pond-living-icons{' in css
    assert '.living-status-warning{' in css
    assert '.pond-weather-grid' not in css
    assert 'weatherWarning' in js and 'moonLabel' in js
    assert 'weatherScene(kind)' in js
    assert '@keyframes weatherRain' in css


def test_v08742_visible_routing_uses_agent_names_not_legacy_role_labels():
    index=(ROOT/'static/index.html').read_text(encoding='utf-8')
    assert '<span>Stella</span><b id="route-chief">' in index
    assert '<span>Rose</span><b id="route-research">' in index
    assert '<span>Percy</span><b id="route-programs">' in index
    assert '<span>Stewart</span><b id="route-caretaker">' in index
    assert '<span>Chief</span><b id="route-chief">' not in index
    assert '<span>Caretaker</span><b id="route-caretaker">' not in index



def test_v08742_ask_the_campus_replaces_project_first_dashboard():
    root = Path(__file__).resolve().parents[1]
    index = (root / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "ASK THE CAMPUS" in index
    assert 'id="campus-agent"' in index
    for name in ("Stella", "Percy", "Rose", "Stewart", "Vernadette", "Poe"):
        assert name in index
    assert 'id="project-form"' not in index
    assert 'id="campus-ask-form"' in index
    assert "/api/campus/ask" in js
    assert "data-campus-create-project" in js


def test_v08742_removes_redundant_dashboard_agent_and_concept_boxes():
    root = Path(__file__).resolve().parents[1]
    index = (root / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "Active Agents" not in index
    assert 'class="victorian-panel concept-mini"' not in index
    assert 'class="victorian-panel barn-mini"' not in index
    assert "View full character sheet" in js
    assert "View full barn concept" in js
    assert 'chief-team-status' in index and 'operations-team-status' in index


def test_v08742_campus_router_intents_and_project_guard():
    assert campus._campus_auto_route("What should I focus on today?") == "stella"
    assert campus._campus_auto_route("Will it rain tomorrow?") == "stewart"
    assert campus._campus_auto_route("Is today a good day to paint the house?") == "stewart"
    assert campus._campus_auto_route("Help me structure a 45 minute class") == "percy"
    assert campus._campus_auto_route("Research the history of this practice") == "rose"
    assert campus._campus_auto_route("Find grants for rural education") == "vernadette"
    assert campus._campus_auto_route("Poe, clock me in for farm work") == "poe"
    assert campus._campus_explicit_project_intent("Create a project for the greenhouse repair") is True
    assert campus._campus_explicit_project_intent("What should I focus on today?") is False


def test_v08742_campus_ask_daily_and_weather_are_local(tmp_path, monkeypatch):
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "ask.db")
    campus.init_db()
    daily = asyncio.run(campus.api_campus_ask(campus.CampusAskRequest(text="What should I focus on today?", agent="auto")))
    assert daily["agent"] == "stella"
    assert daily["mode"] == "deterministic"
    assert daily["additional_ai_calls"] == 0
    assert daily["project_created"] is False
    weather = asyncio.run(campus.api_campus_ask(campus.CampusAskRequest(text="What is the weather tomorrow?", agent="auto")))
    assert weather["agent"] == "stewart"
    assert weather["mode"] == "deterministic"
    assert weather["additional_ai_calls"] == 0
    assert weather["open_panel"] == "environment"


def test_campus_calendar_intent_is_narrow_and_resolves_supported_targets():
    should_match = [
        "What do I have tomorrow?", "What is on my calendar today?", "What should my focus be tomorrow?",
        "Do I have any meetings Tuesday?", "What's happening this week?", "What's my schedule Friday?",
        "Anything going on tomorrow?",
    ]
    should_not_match = [
        "How should I run better meetings?", "What is a project schedule?", "Tell me about calendar design.",
        "What should our event strategy be?",
    ]
    assert all(campus._campus_calendar_intent(text) for text in should_match)
    assert not any(campus._campus_calendar_intent(text) for text in should_not_match)
    monday = campus.date(2026, 9, 14)
    assert campus._campus_calendar_target("tomorrow", monday)["date"] == campus.date(2026, 9, 15)
    assert campus._campus_calendar_target("Tuesday", monday)["date"] == campus.date(2026, 9, 15)
    week = campus._campus_calendar_target("this week", monday)
    assert (week["start"], week["end"]) == (monday, campus.date(2026, 9, 20))


def test_campus_calendar_answers_are_local_mixed_source_and_cancel_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "ask-calendar.db")
    campus.init_db()
    async def unexpected_ai(*_args, **_kwargs):
        raise AssertionError("Recognized calendar requests must not call AI.")
    monkeypatch.setattr(campus, "_campus_ai_advice", unexpected_ai)
    with campus.db() as conn:
        today = campus.date.fromisoformat(campus.environment_summary(conn)["local_date"])
        tomorrow = today + campus.timedelta(days=1)
        now = campus.utc_now()
        project_id = conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES('Calendar Project','Active',?,?)", (now,now)).lastrowid
        common = (tomorrow.isoformat(), now, now)
        conn.execute("""INSERT INTO events(title,event_date,start_time,end_time,all_day,location,event_type,commitment_level,project_id,notes,status,created_by,created_at,updated_at,source)
            VALUES('Manual planning',?,'09:00','10:00',0,'Mavis Manor','Meeting','Normal',?,'local note','Scheduled','Human',?,?,'campus')""", (tomorrow.isoformat(),project_id,now,now))
        conn.execute("""INSERT INTO events(title,event_date,start_time,end_time,all_day,location,event_type,commitment_level,notes,status,created_by,created_at,updated_at,source,external_calendar_id,external_event_id)
            VALUES('Google appointment',?,'14:00','15:00',0,'Library of Mavis','Personal','Major','','Scheduled','Google Calendar',?,?,'google_calendar','primary','g-ask')""", common)
        conn.execute("""INSERT INTO events(title,event_date,all_day,location,event_type,commitment_level,notes,status,created_by,created_at,updated_at,source)
            VALUES('Cancelled item',?,1,'Pond','Other','Normal','','Cancelled','Human',?,?,'campus')""", common)
        before = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("events","projects","tasks","ai_calls","activity_log","community_contributions","contribution_offers","library_materials")}
    result = asyncio.run(campus.api_campus_ask(campus.CampusAskRequest(text="What do I have tomorrow?", agent="percy")))
    assert result["mode"] == "deterministic" and result["agent"] == "stella" and result["additional_ai_calls"] == 0
    assert result["route_source"] == "calendar_intent" and result["open_panel"] == "calendar"
    assert tomorrow.isoformat() not in result["message"]  # human-readable exact date is used
    assert str(tomorrow.year) in result["message"] and str(tomorrow.day) in result["message"]
    assert {x["title"] for x in result["calendar_events"]} == {"Manual planning","Google appointment"}
    assert all(text in result["message"] for text in ("09:00", "Mavis Manor", "Meeting", "Normal commitment", "Calendar Project", "14:00", "Library of Mavis", "Personal", "Major commitment"))
    named = asyncio.run(campus.api_campus_ask(campus.CampusAskRequest(text=f"Do I have any meetings {tomorrow.strftime('%A')}?")))
    assert named["resolved_time"] == campus._campus_calendar_date_label(tomorrow)
    assert campus._campus_calendar_date_label(tomorrow) in named["message"]
    week = asyncio.run(campus.api_campus_ask(campus.CampusAskRequest(text="What's happening this week?")))
    assert "the next seven days" in week["resolved_time"] and "the next seven days" in week["message"]
    with campus.db() as conn:
        after = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in before}
    assert after == before
    empty = asyncio.run(campus.api_campus_ask(campus.CampusAskRequest(text="Anything going on today?")))
    assert "nothing scheduled" in empty["message"].lower() and str(today.year) in empty["message"]


def test_tomorrow_focus_reuses_steward_pressure_without_current_session(tmp_path, monkeypatch):
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "tomorrow-focus.db")
    campus.init_db()
    async def unexpected_ai(*_args, **_kwargs):
        raise AssertionError("Tomorrow focus must remain deterministic.")
    monkeypatch.setattr(campus, "_campus_ai_advice", unexpected_ai)
    with campus.db() as conn:
        today = campus.date.fromisoformat(campus.environment_summary(conn)["local_date"])
        tomorrow = today + campus.timedelta(days=1)
        now = campus.utc_now()
        person_id = conn.execute("INSERT INTO people(display_name,person_type,status,is_primary_user,created_at,updated_at) VALUES('Primary Person','Staff','Active',1,?,?)", (now,now)).lastrowid
        conn.execute("INSERT INTO work_sessions(person_id,participation_type,started_at,notes,created_by,created_at,updated_at) VALUES(?,'Volunteer',?,'Current work','Poe',?,?)", (person_id,now,now,now))
        project_id = conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES('Tomorrow Project','Active',?,?)", (now,now)).lastrowid
        conn.execute("INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,'Prepare locally','programs','Waiting',1,'',?,?)", (project_id,now,now))
        for index in range(2):
            conn.execute("INSERT INTO events(title,event_date,all_day,location,event_type,commitment_level,project_id,notes,status,created_by,created_at,updated_at) VALUES(?,?,1,'Library','Meeting','Major',?,'','Scheduled','Human',?,?)", (f"Tomorrow commitment {index+1}",tomorrow.isoformat(),project_id,now,now))
    result = asyncio.run(campus.api_campus_ask(campus.CampusAskRequest(text="What should my focus be tomorrow?")))
    steward = result["daily_steward"]
    assert result["mode"] == "deterministic" and result["additional_ai_calls"] == 0
    assert steward["local_date"] == tomorrow.isoformat() and steward["focus_cap"] == 1
    assert steward["calendar_pressure"] == {"today_count":2,"major_today_count":2}
    assert all(item.get("kind") != "continue_session" for item in steward["focus"])


def test_tomorrow_focus_surfaces_steward_recommendation_and_calendar_commitment(tmp_path, monkeypatch):
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "tomorrow-focus-message.db")
    campus.init_db()
    async def unexpected_ai(*_args, **_kwargs):
        raise AssertionError("Tomorrow focus must remain deterministic.")
    monkeypatch.setattr(campus, "_campus_ai_advice", unexpected_ai)
    with campus.db() as conn:
        today = campus.date.fromisoformat(campus.environment_summary(conn)["local_date"])
        tomorrow = today + campus.timedelta(days=1)
        now = campus.utc_now()
        conn.execute("""INSERT INTO events(title,event_date,start_time,end_time,all_day,location,event_type,commitment_level,notes,status,created_by,created_at,updated_at,source)
            VALUES('Saving Documents',?,'17:00','18:00',0,'Craft Memorial Library','Class / Program','Normal','','Scheduled','Human',?,?,'campus')""", (tomorrow.isoformat(),now,now))
    result = asyncio.run(campus.api_campus_ask(campus.CampusAskRequest(text="What should my focus be tomorrow?")))
    assert result["mode"] == "deterministic" and result["additional_ai_calls"] == 0
    assert "Saving Documents" in result["message"] and "17:00" in result["message"] and "18:00" in result["message"]
    assert "Craft Memorial Library" in result["message"]
    assert result["daily_steward"]["focus"][0]["title"] in result["message"]


def test_future_steward_keeps_human_gate_and_blocker_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "future-precedence.db")
    campus.init_db()
    with campus.db() as conn:
        today = campus.date.fromisoformat(campus.environment_summary(conn)["local_date"])
        target = today + campus.timedelta(days=2)
        now = campus.utc_now()
        project_id = conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES('Gated Project','Active',?,?)", (now,now)).lastrowid
        conn.execute("INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,'Blocked first','research','Blocked',1,'',?,?)", (project_id,now,now))
        conn.execute("INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,'Calendar-supported task','programs','Waiting',2,'',?,?)", (project_id,now,now))
        conn.execute("INSERT INTO approvals(project_id,title,summary,status,created_at,updated_at) VALUES(?,'Human decision','Review','Pending',?,?)", (project_id,now,now))
        conn.execute("INSERT INTO events(title,event_date,all_day,location,event_type,commitment_level,project_id,notes,status,created_by,created_at,updated_at) VALUES('Linked commitment',?,1,'Library','Meeting','Normal',?,'','Scheduled','Human',?,?)", (target.isoformat(),project_id,now,now))
        steward = campus.daily_steward(conn, target)
    assert steward["focus"][0]["kind"] == "decision" and steward["focus"][0]["title"] == "Human decision"


def test_external_advisor_prompts_exclude_all_calendar_content(tmp_path, monkeypatch):
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "prompt-calendar-privacy.db")
    campus.init_db()
    sentinels = ("PRIVATE EVENT TITLE 8675309", "PRIVATE LOCATION 8675309", "PRIVATE CALENDAR NOTE 8675309")
    with campus.db() as conn:
        today = campus.environment_summary(conn)["local_date"]
        now = campus.utc_now()
        conn.execute("INSERT INTO events(title,event_date,start_time,end_time,all_day,location,event_type,commitment_level,notes,status,created_by,created_at,updated_at,source,external_calendar_id,external_event_id) VALUES(?,?,'10:00','11:00',0,?,'Class / Program','Major',?,'Scheduled','Google Calendar',?,?,'google_calendar','primary','private-prompt-event')", (sentinels[0],today,sentinels[1],sentinels[2],now,now))
        prompts = [campus._campus_advisor_prompt(agent, "Give ordinary advice", conn) for agent in ("stella","percy","rose","stewart")]
    assert all(sentinel not in prompt for prompt in prompts for sentinel in sentinels)


def test_v097_rose_library_inventory_confirms_empty_without_ai_or_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "rose-library-empty.db")
    campus.init_db()

    async def unexpected_ai(*_args, **_kwargs):
        raise AssertionError("Recognized Library inventory requests must not call AI.")

    monkeypatch.setattr(campus, "_campus_ai_advice", unexpected_ai)
    tracked = ("library_collections", "library_materials", "library_inbox", "ai_calls", "activity_log", "contribution_offers", "community_contributions")
    with campus.db() as conn:
        before = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tracked}

    prompt = "Search only the local Library. What materials are currently available? Show their titles and formats. If it is empty, say so. Do not search the web or create anything."
    result = asyncio.run(campus.api_campus_ask(campus.CampusAskRequest(text=prompt, agent="auto")))

    assert result["agent"] == "rose"
    assert result["mode"] == "deterministic"
    assert result["message"] == "No Cataloged materials in Active collections."
    assert result["library_inventory"] == []
    assert result["local_only"] is True and result["web_access"] is False
    assert result["additional_ai_calls"] == 0 and result["project_created"] is False
    with campus.db() as conn:
        after = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tracked}
    assert after == before


def test_v097_rose_library_inventory_lists_exact_trusted_titles_and_types(tmp_path, monkeypatch):
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "rose-library-list.db")
    campus.init_db()
    now = campus.utc_now()
    with campus.db() as conn:
        active_id = conn.execute(
            "INSERT INTO library_collections(title,collection_type,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("Current Collection", "Class", "Active", "Human", now, now),
        ).lastrowid
        inactive_id = conn.execute(
            "INSERT INTO library_collections(title,collection_type,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            ("Inactive Collection", "Class", "Archived", "Human", now, now),
        ).lastrowid
        for collection_id, title, material_type, status in (
            (active_id, "Apple Notes", "Instructor Notes", "Cataloged"),
            (active_id, "Barn Plan v2", "Presentation", "Cataloged"),
            (active_id, "Unreviewed Draft", "Document", "Incoming"),
            (inactive_id, "Old Handout", "Handout", "Cataloged"),
        ):
            conn.execute(
                "INSERT INTO library_materials(collection_id,title,material_type,status,source_kind,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (collection_id, title, material_type, status, "manual", "Human", now, now),
            )

    async def unexpected_ai(*_args, **_kwargs):
        raise AssertionError("Inventory listing must not call AI.")

    monkeypatch.setattr(campus, "_campus_ai_advice", unexpected_ai)
    result = asyncio.run(campus.api_campus_ask(campus.CampusAskRequest(text="Show the local Library materials and formats.", agent="rose")))
    assert result["library_inventory"] == [
        {"title": "Apple Notes", "material_type": "Instructor Notes"},
        {"title": "Barn Plan v2", "material_type": "Presentation"},
    ]
    assert "Apple Notes — Instructor Notes" in result["message"]
    assert "Barn Plan v2 — Presentation" in result["message"]
    assert "Unreviewed Draft" not in result["message"] and "Old Handout" not in result["message"]
    assert set(result["library_inventory"][0]) == {"title", "material_type"}


def test_v097_rose_library_inventory_reports_retrieval_failure_not_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "rose-library-unavailable.db")
    campus.init_db()

    def unavailable(_conn):
        raise campus.sqlite3.OperationalError("simulated read failure")

    async def unexpected_ai(*_args, **_kwargs):
        raise AssertionError("Failed inventory retrieval must not fall back to AI.")

    monkeypatch.setattr(campus, "library_inventory_rows", unavailable)
    monkeypatch.setattr(campus, "_campus_ai_advice", unexpected_ai)
    result = asyncio.run(campus.api_campus_ask(campus.CampusAskRequest(text="What materials are available in the Library?", agent="auto")))
    assert result["status"] == "unavailable"
    assert result["library_inventory"] is None
    assert "retrieval failed" in result["message"].lower()
    assert "no cataloged materials" not in result["message"].lower()
    assert result["additional_ai_calls"] == 0 and result["web_access"] is False


def test_v097_rose_library_inventory_intent_does_not_capture_topic_search():
    assert campus._campus_library_inventory_intent("Search the local Library for tincture safety guidance.") is False
    assert campus._campus_library_inventory_intent("Research the history of barn construction in the Library.") is False
    assert campus._campus_auto_route("Search the local Library for tincture safety guidance.") == "rose"
    assert campus._campus_library_inventory_intent("What materials are currently available in the local Library?") is True


def test_monthly_participation_uses_selected_person_month_and_completed_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "monthly-participation.db")
    campus.init_db()
    alice = asyncio.run(campus.api_person_create(campus.PersonRequest(display_name="Alice Example", person_type="Volunteer")))
    bob = asyncio.run(campus.api_person_create(campus.PersonRequest(display_name="Bob Example", person_type="Volunteer")))
    with campus.db() as conn:
        activity_id = int(conn.execute("SELECT id FROM activity_categories ORDER BY id LIMIT 1").fetchone()[0])
        now = campus.utc_now()
        conn.execute("INSERT INTO work_sessions(person_id,activity_category_id,participation_type,started_at,ended_at,duration_minutes,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (alice["person_id"],activity_id,"Volunteer","2026-08-05T13:00:00+00:00","2026-08-05T14:30:00+00:00",90,"Garden support","Poe",now,now))
        conn.execute("INSERT INTO work_sessions(person_id,activity_category_id,participation_type,started_at,ended_at,duration_minutes,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,NULL,NULL,?,?,?,?)", (alice["person_id"],activity_id,"Volunteer","2026-08-12T13:00:00+00:00","Open session","Poe",now,now))
        conn.execute("INSERT INTO work_sessions(person_id,activity_category_id,participation_type,started_at,ended_at,duration_minutes,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (alice["person_id"],activity_id,"Volunteer","2026-09-03T13:00:00+00:00","2026-09-03T14:00:00+00:00",60,"Following month","Poe",now,now))
        conn.execute("INSERT INTO work_sessions(person_id,activity_category_id,participation_type,started_at,ended_at,duration_minutes,notes,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (bob["person_id"],activity_id,"Volunteer","2026-08-06T13:00:00+00:00","2026-08-06T18:00:00+00:00",300,"Other person","Poe",now,now))
    asyncio.run(campus.api_work_manual(campus.WorkManualRequest(person_id=alice["person_id"],work_date="2026-08-10",activity_category_id=activity_id,duration_minutes=120,description="Prepared class materials")))

    august = asyncio.run(campus.api_monthly_participation(alice["person_id"], "2026-08"))
    september = asyncio.run(campus.api_monthly_participation(alice["person_id"], "2026-09"))
    assert august["total_minutes"] == 210 and august["total_hours"] == 3.5
    assert august["remaining_minutes"] == 4590 and august["target_hours"] == 80
    assert [item["local_date"] for item in august["sessions"]] == ["2026-08-05", "2026-08-10"]
    assert {item["notes"] for item in august["sessions"]} == {"Garden support", "Prepared class materials"}
    assert september["total_minutes"] == 60
    with campus.db() as conn:
        manual = conn.execute("SELECT entry_mode,duration_minutes FROM work_sessions WHERE person_id=? AND work_date='2026-08-10'", (alice["person_id"],)).fetchone()
        assert tuple(manual) == ("manual_duration", 120)
        assert conn.execute("SELECT COUNT(*) FROM work_session_audit WHERE work_session_id=(SELECT id FROM work_sessions WHERE person_id=? AND work_date='2026-08-10')", (alice["person_id"],)).fetchone()[0] == 1


def test_monthly_participation_csv_is_exact_and_organizations_have_no_target(tmp_path, monkeypatch):
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "monthly-csv.db")
    campus.init_db()
    person = asyncio.run(campus.api_person_create(campus.PersonRequest(display_name="Sam Person", entity_kind="Person")))
    organization = asyncio.run(campus.api_person_create(campus.PersonRequest(display_name="Sam Organization", entity_kind="Organization", person_type="Community Organization")))
    with campus.db() as conn:
        activity_id = int(conn.execute("SELECT id FROM activity_categories ORDER BY id LIMIT 1").fetchone()[0])
    asyncio.run(campus.api_work_manual(campus.WorkManualRequest(person_id=person["person_id"],work_date="2026-07-04",activity_category_id=activity_id,duration_minutes=75,description="Community event setup")))
    response = asyncio.run(campus.api_monthly_participation_csv(person["person_id"], "2026-07"))
    text = response.body.decode("utf-8-sig")
    assert "Sam Person" in text and "2026-07-04" in text and "Community event setup" in text
    assert "Monthly Total" in text and ",75,1.25" in text
    assert "Sam Organization" not in text and "2026-08" not in text
    org_record = asyncio.run(campus.api_monthly_participation(organization["person_id"], "2026-07"))
    assert org_record["target_minutes"] is None and org_record["remaining_minutes"] is None
    assert org_record["target_reached"] is False


def test_people_participation_ui_structure_and_existing_boundaries_remain():
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/app.css").read_text(encoding="utf-8")
    assert "Directory" in js and "Work Hours" in js and "Contributions" in js
    assert "Add Person" in js and "Add Organization" in js and "More details" in js
    assert "Monthly Participation Record" in js and "Print Monthly Record" in js and "Download CSV" in js
    assert "Tracking target only; this is not an eligibility determination." in js
    assert "@media print" in css and ".print-monthly-record" in css
    assert "/api/work-report.csv" in js and "/api/community-contributions" in js
    assert "_campus_library_inventory_intent" in app_text and "No Cataloged materials in Active collections." in app_text
    assert "Medicaid" not in app_text and "Medicaid" not in js


def test_v08742_campus_ask_explicit_project_requires_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "ask-project.db")
    campus.init_db()
    result = asyncio.run(campus.api_campus_ask(campus.CampusAskRequest(text="Create a project for repairing the greenhouse", agent="auto")))
    assert result["suggest_project"] is True
    assert result["project_created"] is False
    with campus.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0


def test_ask_the_campus_frontend_regression_guards():
    root = Path(__file__).resolve().parents[1]
    js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
    index = (root / "static" / "index.html").read_text(encoding="utf-8")
    assert "let campusAskSubmitting = false;" in js
    assert "let campusAskLastResult = null;" in js
    assert "let campusAskHistory = [];" in js
    assert "campus-ask-thread" in js
    assert "scrollIntoView" in js
    assert "grantDiscoveryResult={provider:result.vernadette_result.provider" in js
    assert "grantDiscovery={provider:result.vernadette_result.provider" not in js
    assert f"app.js?v={LIVE_CACHE_KEY}" in index


def test_v08742_campus_routing_reason_and_followup():
    import app as campus
    route, reason, source = campus._campus_auto_route_detail("Is today a good day to paint the house?")
    assert route == "stewart"
    assert "weather" in reason.lower()
    assert source == "auto"
    route2, reason2, source2 = campus._campus_auto_route_detail("What about tomorrow?", "stewart")
    assert route2 == "stewart"
    assert source2 == "followup"
    assert "follow-up" in reason2.lower()


def test_v08742_ask_request_supports_previous_agent_and_selected_reason():
    import app as campus
    req = campus.CampusAskRequest(text="Can you make that simpler?", agent="auto", previous_agent="percy")
    assert req.previous_agent == "percy"
    route, _, source = campus._campus_auto_route_detail(req.text, req.previous_agent)
    assert route == "percy" and source == "followup"


def test_v08742_ask_ui_polish_and_cache_key():
    root = Path(__file__).resolve().parents[1]
    index = (root / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
    css = (root / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert LIVE_SHELL_LABEL in index
    assert f"app.js?v={LIVE_CACHE_KEY}" in index and f"app.css?v={LIVE_CACHE_KEY}" in index and f"world.css?v={LIVE_CACHE_KEY}" in index
    assert 'id="campus-ask-clear"' in index
    assert "previous_agent:previousAgent" in js
    assert "CAMPUS_ASK_SESSION_KEY" in js
    assert "Ctrl+Enter sends" in index
    assert ".campus-route-note" in css


def test_v08742_cleanup_wording_uses_rose_and_ask_campus():
    root = Path(__file__).resolve().parents[1]
    js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "Use Create a Project to start the first one" not in js
    assert "ask Rose to research it beyond the trusted Library" in js


def test_v08742_living_campus_ambient_movement_and_newest_first_ask_history():
    root = Path(__file__).resolve().parents[1]
    index = (root / "static" / "index.html").read_text(encoding="utf-8")
    js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
    app_css = (root / "static" / "css" / "app.css").read_text(encoding="utf-8")
    world_css = (root / "static" / "css" / "world.css").read_text(encoding="utf-8")
    assert LIVE_BUILD in index
    assert f"app.js?v={LIVE_CACHE_KEY}" in index and f"app.css?v={LIVE_CACHE_KEY}" in index and f"world.css?v={LIVE_CACHE_KEY}" in index
    assert "function startAmbientMovement()" in js
    assert "function ambientTravelAgent(agent,destinationNode" in js
    assert "agentCanAmbientWander" in js
    assert "cross-campus social movement" in world_css
    assert "Walking with ${companionName}" in js
    assert "findNodeRoute(startNode,destinationNode)" in js
    assert "campusAskHistory.unshift" in js
    assert "CAMPUS_ASK_HISTORY_LIMIT = 20" in js
    assert "Newest response first · scroll down for older exchanges" in js
    assert "max-height:390px" in app_css and "overflow-y:auto" in app_css


def test_phenology_observation_suggestion_and_rose_review(tmp_path, monkeypatch):
    import asyncio
    import app as campus
    original = campus.DB_PATH
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "phenology.db")
    try:
        campus.init_db()
        manual = asyncio.run(campus.api_phenology_create(campus.PhenologyObservationRequest(
            subject="Apple tree", stage="first bloom", observation_date="2026-04-11",
            location_area="Fruit Forest", source="human observation", status="observed", notes="Three open blossoms."
        )))
        assert manual["observation"]["status"] == "observed"
        assert manual["observation"]["source"] == "human observation"
        assert manual["observation"]["location_area"] == "Fruit Forest"
        suggested = asyncio.run(campus.api_phenology_create(campus.PhenologyObservationRequest(
            subject="Spring peepers", stage="first heard", observation_date="2026-03-18",
            location_area="Pond", source="system suggestion", status="confirmed", notes="Please verify."
        )))
        assert suggested["observation"]["status"] == "suggested"
        confirmed = asyncio.run(campus.api_phenology_review(suggested["observation"]["id"], campus.PhenologyReviewRequest(status="confirmed")))
        assert confirmed["observation"]["status"] == "confirmed"
        assert confirmed["observation"]["review_agent_id"] == "research"
        rejected = asyncio.run(campus.api_phenology_create(campus.PhenologyObservationRequest(
            subject="Frost", stage="first frost", observation_date="2026-10-09",
            location_area="Mavis Manor", source="system suggestion", notes="Near-freezing reading."
        )))
        reviewed = asyncio.run(campus.api_phenology_review(rejected["observation"]["id"], campus.PhenologyReviewRequest(status="rejected", notes="No frost observed.")))
        assert reviewed["observation"]["status"] == "rejected"
        assert reviewed["observation"]["notes"] == "No frost observed."
        with campus.db() as conn:
            entries = campus.environment_summary(conn)["phenology_observations"]
        assert {entry["status"] for entry in entries} == {"observed", "confirmed", "rejected"}
    finally:
        campus.DB_PATH = original


def test_phenology_watchlist_seed_custom_status_and_suggestion(tmp_path, monkeypatch):
    import asyncio
    import app as campus
    original=campus.DB_PATH; monkeypatch.setattr(campus,"DB_PATH",tmp_path/"watch.db")
    try:
        campus.init_db()
        with campus.db() as conn: seeded=campus.environment_summary(conn)["phenology_watchlist"]
        grapes=next(item for item in seeded if item["subject"]=="Grapes")
        assert "veraison" in grapes["stages"] and grapes["status"]=="Active"
        custom=asyncio.run(campus.api_phenology_watchlist_create(campus.PhenologyWatchlistRequest(subject="Pawpaw",category="Food & garden plants",location_area="Fruit Forest",stages=["first bloom","ripe"],notes="")))["watchlist"]
        assert custom["stages"]==["first bloom","ripe"]
        asyncio.run(campus.api_phenology_watchlist_status(custom["id"],campus.LibraryCollectionStatusRequest(status="Inactive")))
        with campus.db() as conn: assert not [x for x in campus.environment_summary(conn)["phenology_observations"] if x["subject"]=="Pawpaw"]
        suggestion=asyncio.run(campus.api_phenology_watchlist_suggest(grapes["id"]))["observation"]
        assert suggestion["status"]=="suggested" and suggestion["source"]=="system suggestion"
    finally: campus.DB_PATH=original


def test_phenology_history_uses_trusted_normalized_records(tmp_path, monkeypatch):
    import asyncio
    import app as campus
    old=campus.DB_PATH; monkeypatch.setattr(campus,"DB_PATH",tmp_path/"history.db")
    try:
        campus.init_db()
        for subject,stage,when,status,location in [(" Ironweed "," First Bloom ","2024-08-07","observed","Fruit Forest"),("ironweed","first bloom","2025-08-02","confirmed","Mavis Manor"),("Ironweed","first bloom","2026-07-29","suggested","Fruit Forest"),("Ironweed","first bloom","2027-08-09","rejected","Fruit Forest")]:
            asyncio.run(campus.api_phenology_create(campus.PhenologyObservationRequest(subject=subject,stage=stage,observation_date=when,location_area=location,source="human observation" if status!="suggested" else "system suggestion",status=status)))
        with campus.db() as conn: history=campus.phenology_history(conn,"IRONWEED","first bloom")
        assert [r["year"] for r in history["records"]]==[2024,2025]
        assert history["statistics"]["years_recorded"]==2 and history["statistics"]["earliest_date"]=="2024-08-07"
        with campus.db() as conn: local=campus.phenology_history(conn,"ironweed","first bloom","Fruit Forest")
        assert len(local["records"])==1 and local["records"][0]["location_area"]=="Fruit Forest"
    finally: campus.DB_PATH=old


def test_seasonal_context_trust_recency_weather_and_read_only(tmp_path, monkeypatch):
    import asyncio
    from datetime import timedelta
    import app as campus
    old=campus.DB_PATH; monkeypatch.setattr(campus,"DB_PATH",tmp_path/"context.db")
    try:
        campus.init_db()
        with campus.db() as conn:
            today=campus.date.fromisoformat(campus.environment_summary(conn)["local_date"])
            now=campus.utc_now()
            for subject,status,when in [("Observed plant","observed",today),("Confirmed plant","confirmed",today),("Suggested plant","suggested",today),("Rejected plant","rejected",today),("Recency boundary plant","observed",today-timedelta(days=45)),("Stale plant","observed",today-timedelta(days=46))]:
                conn.execute("INSERT INTO phenology_observations(subject,stage,observation_date,location_area,status,source,notes,review_agent_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(subject,"first bloom",when.isoformat(),"Fruit Forest",status,"human observation","","research",now,now))
            conn.execute("INSERT INTO phenology_checks(subject,stage,location_area,reason,status,rose_agent_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",("Sunchokes","first flower","Fruit Forest","Worth checking.","pending","research",now,now))
            conn.execute("INSERT OR REPLACE INTO weather_current(id,source,source_kind,summary,updated_at) VALUES(1,?,?,?,?)",("Open-Meteo fallback","model_fallback","Warm and humid",now))
            before={table:conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("phenology_observations","phenology_checks","tasks")}
            context=campus.seasonal_context(conn)
            after={table:conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in before}
        assert before==after
        assert {item["subject"] for item in context["observed_now"]}=={"Observed plant","Confirmed plant","Recency boundary plant"}
        assert {item["provenance"] for item in context["observed_now"]}=={"human observation","Rose confirmed observation"}
        assert context["worth_checking"][0]["subject"]=="Sunchokes"
        assert context["worth_checking"][0]["provenance"]=="Rose seasonal check"
        assert "Sunchokes" not in {item["subject"] for item in context["observed_now"]}
        assert context["weather"]=={"summary":"Warm and humid","source":"Open-Meteo fallback","provenance":"normalized MDC weather"}
        response=asyncio.run(campus.api_seasonal_context())
        assert {"generated_at","calendar_date","season","recency_days","observed_now","worth_checking","weather"}.issubset(response)
        assert response["recency_days"]==45
        with campus.db() as conn:
            conn.execute("DELETE FROM weather_current")
            unavailable=campus.seasonal_context(conn)
        assert unavailable["weather"]["summary"]=="Weather unavailable"
        assert unavailable["weather"]["source"]=="Unavailable"
    finally: campus.DB_PATH=old


def test_stella_seasonal_context_handoff_is_read_only_and_optional(tmp_path, monkeypatch):
    import asyncio
    import app as campus
    old = campus.DB_PATH
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "stella-seasonal-context.db")
    try:
        campus.init_db()
        with campus.db() as conn:
            today = campus.environment_summary(conn)["local_date"]
            now = campus.utc_now()
            for subject, status, source in [
                ("Ironweed", "observed", "human observation"),
                ("Grapes", "confirmed", "system suggestion"),
                ("Sunchokes", "suggested", "system suggestion"),
            ]:
                conn.execute(
                    "INSERT INTO phenology_observations(subject,stage,observation_date,location_area,status,source,notes,review_agent_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (subject, "full bloom", today, "Fruit Forest", status, source, "", "research", now, now),
                )
            conn.execute(
                "INSERT INTO phenology_checks(subject,stage,location_area,reason,status,rose_agent_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                ("Sunchokes", "first flower", "Fruit Forest", "Worth checking.", "pending", "research", now, now),
            )
            conn.execute(
                "INSERT OR REPLACE INTO weather_current(id,source,source_kind,summary,updated_at) VALUES(1,?,?,?,?)",
                ("Open-Meteo fallback", "model_fallback", "Warm and humid", now),
            )
            before = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("phenology_observations", "phenology_checks", "tasks")}
            daily_before = campus.daily_steward(conn)

        result = asyncio.run(campus.api_campus_ask(campus.CampusAskRequest(text="What has Rose observed recently?", agent="auto")))
        assert result["agent"] == "stella"
        assert result["mode"] == "deterministic"
        assert result["additional_ai_calls"] == 0
        context = result["seasonal_context"]
        assert {item["subject"] for item in context["observed_now"]} == {"Ironweed", "Grapes"}
        assert {item["provenance"] for item in context["observed_now"]} == {"human observation", "Rose confirmed observation"}
        assert context["worth_checking"] == [{"subject": "Sunchokes", "stage": "first flower", "location": "Fruit Forest", "reason": "Worth checking.", "provenance": "Rose seasonal check"}]
        assert context["weather"]["source"] == "Open-Meteo fallback"
        assert "Worth checking, not established observations" in result["message"]

        with campus.db() as conn:
            after = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in before}
            daily_after = campus.daily_steward(conn)
        assert after == before
        assert daily_after["focus"] == daily_before["focus"]
        assert daily_after["watch"] == daily_before["watch"]

        def unavailable(_conn):
            raise RuntimeError("Seasonal Context unavailable")

        monkeypatch.setattr(campus, "seasonal_context", unavailable)
        unavailable_result = asyncio.run(campus.api_campus_ask(campus.CampusAskRequest(text="What is the current seasonal context?", agent="stella")))
        assert unavailable_result["agent"] == "stella"
        assert unavailable_result["seasonal_context"] is None
        assert "unavailable" in unavailable_result["message"].lower()
    finally:
        campus.DB_PATH = old


def test_v096_seasonal_context_transparency_ui_and_release_contract():
    import json
    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/app.css").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "static/assets/asset-manifest.json").read_text(encoding="utf-8"))
    assert LIVE_VERSION == "0.9.7"
    assert LIVE_CACHE_KEY == "098"
    assert "Rose’s Seasonal Briefing" in js
    assert "getJson('/api/environment/seasonal-context')" in js
    assert "Observed Now" in js and "established observations" in js
    assert "item.date" in js and "item.location" in js and "item.provenance" in js
    assert "Worth Checking" in js and "not yet an established observation" in js
    assert "Rose seasonal check" in js
    assert ".seasonal-observation" in css and ".seasonal-check" in css
    assert "Weather Context" in js and "weather.source" in js
    assert "No recent confirmed or observed phenology records." in js
    assert "Nothing currently waiting for a Rose check." in js
    assert "Seasonal Context unavailable." in js
    assert "data-refresh-seasonal-context" in js
    assert LIVE_SHELL_LABEL in index
    assert f'app.js?v={LIVE_CACHE_KEY}' in index
    assert f'app.css?v={LIVE_CACHE_KEY}' in index
    assert f'world.css?v={LIVE_CACHE_KEY}' in index
    assert manifest["build"] == LIVE_BUILD
    assert manifest["version"] == LIVE_VERSION
    assert manifest["ai_runtime"]["stabilization_recovery"]["schema_version"] == LIVE_VERSION


def test_v097_contribution_offer_fulfillments_direct_and_duplicate_guard(tmp_path, monkeypatch):
    import app as campus
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "contributions.db")
    campus.init_db()
    sam = asyncio.run(campus.api_person_create(campus.PersonRequest(display_name="Sam")))
    with campus.db() as conn:
        now = campus.utc_now()
        project_id = int(conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)", ("Barn Repair", "Active", now, now)).lastrowid)
        event_id = int(conn.execute("INSERT INTO events(title,event_date,all_day,location,event_type,commitment_level,project_id,notes,status,created_by,created_at,updated_at) VALUES(?,?,1,?,?,?,?,?,?,?,?,?)", ("Barn workday", "2026-09-20", "Barn", "Institute", "Normal", project_id, "", "Scheduled", "Human", now, now)).lastrowid)
    offer = asyncio.run(campus.api_contribution_offer_create(campus.ContributionOfferRequest(
        contributor_id=sam["person_id"], contribution_type="goods_materials", description="Lumber for the barn",
        offered_on="2026-09-12", quantity=10, unit="boards", project_id=project_id, event_id=event_id,
    )))
    request = campus.ContributionReceivedRequest(
        contributor_id=sam["person_id"], offer_id=offer["offer_id"], contribution_type="goods_materials",
        description="Delivered six boards", received_on="2026-09-15", quantity=6, unit="boards",
        project_id=project_id, event_id=event_id, submission_key="sam-six-boards",
    )
    received = asyncio.run(campus.api_contribution_received_create(request))
    duplicate = asyncio.run(campus.api_contribution_received_create(request))
    asyncio.run(campus.api_contribution_received_create(campus.ContributionReceivedRequest(
        contributor_id=sam["person_id"], offer_id=offer["offer_id"], contribution_type="goods_materials",
        description="Delivered two more boards", received_on="2026-09-16", quantity=2, unit="boards",
        project_id=project_id, event_id=event_id, submission_key="sam-two-more-boards",
    )))
    direct = asyncio.run(campus.api_contribution_received_create(campus.ContributionReceivedRequest(
        contributor_id=sam["person_id"], contribution_type="goods_materials", description="Two bags of mulch",
        received_on="2026-09-16", quantity=2, unit="bags", submission_key="direct-mulch",
    )))
    ledger = asyncio.run(campus.api_community_contributions())
    saved_offer = next(x for x in ledger["offers"] if x["id"] == offer["offer_id"])
    assert received["status"] == "created" and direct["status"] == "created"
    assert duplicate == {"status":"duplicate", "contribution_id":received["contribution_id"], "message":"This received contribution was already recorded."}
    assert saved_offer["remaining_quantity"] == 2
    assert len(saved_offer["fulfillments"]) == 2
    asyncio.run(campus.api_contribution_offer_update(offer["offer_id"], campus.ContributionOfferUpdateRequest(status="Cancelled")))
    ledger = asyncio.run(campus.api_community_contributions())
    assert next(x for x in ledger["offers"] if x["id"] == offer["offer_id"])["status"] == "Cancelled"
    assert len(ledger["contributions"]) == 3
    with campus.db() as conn:
        conn.execute("UPDATE events SET project_id=NULL WHERE id=?", (event_id,))
        saved = conn.execute("SELECT project_id,event_id FROM community_contributions WHERE id=?", (received["contribution_id"],)).fetchone()
    assert saved["project_id"] == project_id and saved["event_id"] == event_id


def test_v097_identity_links_work_sessions_and_reset_preservation(tmp_path, monkeypatch):
    import app as campus
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "identity-contributions.db")
    campus.init_db()
    sam = asyncio.run(campus.api_person_create(campus.PersonRequest(display_name="Sam")))
    warning = asyncio.run(campus.api_person_create(campus.PersonRequest(display_name=" sam ", entity_kind="Organization")))
    assert warning["status"] == "duplicate_warning" and warning["possible_duplicates"][0]["id"] == sam["person_id"]
    org = asyncio.run(campus.api_person_create(campus.PersonRequest(display_name="Mavis Hardware", entity_kind="Organization", person_type="Sponsor")))
    with campus.db() as conn:
        now = campus.utc_now()
        project_id = int(conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)", ("Library Class", "Active", now, now)).lastrowid)
        other_project = int(conn.execute("INSERT INTO projects(title,status,created_at,updated_at) VALUES(?,?,?,?)", ("Other", "Active", now, now)).lastrowid)
        event_id = int(conn.execute("INSERT INTO events(title,event_date,all_day,location,event_type,commitment_level,project_id,notes,status,created_by,created_at,updated_at) VALUES(?,?,1,?,?,?,?,?,?,?,?,?)", ("Class", "2026-09-21", "Library", "Class / Program", "Normal", project_id, "", "Scheduled", "Human", now, now)).lastrowid)
        task_id = int(conn.execute("INSERT INTO tasks(project_id,title,owner_agent_id,status,sequence,brief,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (project_id,"Thank Sam","operations","Waiting",1,"",now,now)).lastrowid)
        category_id = int(conn.execute("SELECT id FROM activity_categories LIMIT 1").fetchone()[0])
    try:
        asyncio.run(campus.api_work_clock_in(campus.WorkClockInRequest(person_id=org["person_id"], activity_category_id=category_id)))
        assert False, "Organization clock-in should fail"
    except campus.HTTPException as exc:
        assert exc.status_code == 409
    session = asyncio.run(campus.api_work_clock_in(campus.WorkClockInRequest(person_id=sam["person_id"], project_id=project_id, activity_category_id=category_id)))
    asyncio.run(campus.api_work_clock_out(session["session_id"], campus.WorkClockOutRequest()))
    try:
        asyncio.run(campus.api_person_identity_kind(sam["person_id"], campus.IdentityKindRequest(entity_kind="Organization")))
        assert False, "Identity with work should remain Person"
    except campus.HTTPException as exc:
        assert exc.status_code == 409
    contribution = asyncio.run(campus.api_contribution_received_create(campus.ContributionReceivedRequest(
        contributor_id=sam["person_id"], contribution_type="professional_service", description="Class facilitation",
        received_on="2026-09-21", project_id=project_id, event_id=event_id, work_session_id=session["session_id"],
        follow_up_status="Pending", follow_up_task_id=task_id, submission_key="facilitation-session",
    )))
    try:
        asyncio.run(campus.api_contribution_received_create(campus.ContributionReceivedRequest(
            contributor_id=sam["person_id"], contribution_type="professional_service", description="Duplicate facilitation",
            received_on="2026-09-21", work_session_id=session["session_id"], submission_key="different-key",
        )))
        assert False, "One work session must not be counted twice"
    except campus.HTTPException as exc:
        assert exc.status_code == 409
    try:
        asyncio.run(campus.api_contribution_offer_create(campus.ContributionOfferRequest(
            contributor_id=sam["person_id"], contribution_type="goods_materials", description="Conflict",
            offered_on="2026-09-12", project_id=other_project, event_id=event_id,
        )))
        assert False, "Conflicting project/event should fail"
    except campus.HTTPException as exc:
        assert exc.status_code == 400
    campus.reset_runtime()
    with campus.db() as conn:
        saved = conn.execute("SELECT project_id,event_id,work_session_id FROM community_contributions WHERE id=?", (contribution["contribution_id"],)).fetchone()
    assert saved is not None and saved["project_id"] is None and saved["event_id"] == event_id and saved["work_session_id"] == session["session_id"]


def test_v097_contributions_are_on_demand_local_only_and_ui_contract(tmp_path, monkeypatch):
    import app as campus
    monkeypatch.setattr(campus, "DB_PATH", tmp_path / "visibility.db")
    campus.init_db()
    identity = asyncio.run(campus.api_person_create(campus.PersonRequest(display_name="Private Donor")))
    asyncio.run(campus.api_contribution_received_create(campus.ContributionReceivedRequest(
        contributor_id=identity["person_id"], contribution_type="money_sponsorship", description="Restricted class gift",
        received_on="2026-09-12", amount_cents=2500, currency="USD", restrictions="Class supplies only",
        submission_key="private-gift",
    )))
    state = campus.current_state()
    assert "community_contributions" not in state and "contribution_offers" not in state
    assert "Restricted class gift" not in str(state) and "Class supplies only" not in str(state)
    with campus.db() as conn:
        prompt = campus._campus_advisor_prompt("stella", "What matters?", conn)
        activity = str(campus.rows(conn, "SELECT * FROM activity_log"))
    assert "Restricted class gift" not in prompt and "Class supplies only" not in prompt
    assert "Restricted class gift" not in activity and "Class supplies only" not in activity
    index = (ROOT / "static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/app.js").read_text(encoding="utf-8")
    css = (ROOT / "static/css/app.css").read_text(encoding="utf-8")
    assert LIVE_SHELL_LABEL in index and f"app.js?v={LIVE_CACHE_KEY}" in index
    assert "/api/community-contributions" in js and "Local trusted operator only" in js
    assert "data-contribution-offer-form" in js and "data-contribution-received-form" in js
    assert ".contribution-card" in css


def test_v097_additive_identity_migration_preserves_legacy_people(tmp_path, monkeypatch):
    import sqlite3
    import app as campus
    path = tmp_path / "legacy-people.db"
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE people(id INTEGER PRIMARY KEY AUTOINCREMENT,display_name TEXT NOT NULL,person_type TEXT NOT NULL DEFAULT 'Volunteer',status TEXT NOT NULL DEFAULT 'Active',contact_info TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',is_primary_user INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
        conn.execute("INSERT INTO people(id,display_name,person_type,status,contact_info,notes,is_primary_user,created_at,updated_at) VALUES(7,'Legacy Helper','Volunteer','Active','kept contact','kept note',0,'2026-01-01','2026-01-01')")
    monkeypatch.setattr(campus, "DB_PATH", path)
    campus.init_db()
    with campus.db() as conn:
        person = conn.execute("SELECT * FROM people WHERE id=7").fetchone()
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert person["entity_kind"] == "Person"
    assert person["contact_info"] == "kept contact" and person["notes"] == "kept note"
    assert {"contribution_offers", "community_contributions"}.issubset(tables)
