"""Draft, publish, and versioning tests.

These cover the M5 acceptance criteria from the spec (`23-coding-agent-milestones.md`):

- a published version cannot be changed,
- user edits survive a refresh,
- v2 records parent v1.

The interesting assertions are the negative ones. A test that only checks "edit
then read back" passes just as well against an implementation that silently
discards the previous value, so most of what follows checks what must *not*
change.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import COPVersion, Draft, GenerationRun, Project

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "reference-langchain-cop.json"


def load_fixture() -> dict:
    with FIXTURE.open(encoding="utf-8") as handle:
        return json.load(handle)


def create_project(db: Session, title: str = "Draft Project") -> str:
    project = Project(title=title, domain=title, scope="Scope")
    db.add(project)
    db.commit()
    return str(project.id)


def seed_version(db: Session, project_id: str, artifact: dict | None = None) -> str:
    """Publish a version directly, standing in for a Harness-produced v1."""
    version = COPVersion(
        project_id=project_id,
        version_number=1,
        artifact_json=artifact if artifact is not None else load_fixture(),
        change_summary="Initial",
        created_by="harness",
    )
    db.add(version)
    db.commit()
    return str(version.id)


def make_draft(db: Session, project_id: str, artifact: dict | None = None) -> str:
    draft = Draft(
        project_id=project_id,
        artifact_json=artifact if artifact is not None else load_fixture(),
    )
    db.add(draft)
    db.commit()
    return str(draft.id)


def make_completed_run(db: Session, project_id: str, artifact: dict | None = None) -> str:
    run = GenerationRun(
        project_id=project_id,
        status="completed",
        requested_mode="standard",
        candidate_artifact_json=artifact if artifact is not None else load_fixture(),
    )
    db.add(run)
    db.commit()
    return str(run.id)


class TestDraftCreation:
    def test_a_candidate_becomes_the_projects_active_draft(self, client, db):
        project_id = create_project(db)
        run_id = make_completed_run(db, project_id)

        response = client.post(f"/api/v1/projects/{project_id}/drafts/from-run/{run_id}")
        assert response.status_code == 201, response.text
        draft = response.json()
        assert draft["source_run_id"] == run_id
        assert draft["counts"]["goals"] > 0

        read_back = client.get(f"/api/v1/projects/{project_id}/draft")
        assert read_back.status_code == 200
        assert read_back.json()["id"] == draft["id"]

    def test_a_version_can_be_forked_into_a_draft(self, client, db):
        project_id = create_project(db)
        version_id = seed_version(db, project_id)

        response = client.post(f"/api/v1/projects/{project_id}/drafts/from-version/{version_id}")
        assert response.status_code == 201, response.text
        assert response.json()["base_version_id"] == version_id

    def test_creating_a_second_draft_is_refused_rather_than_overwriting(self, client, db):
        """A project has at most one active draft; the first must not be lost."""
        project_id = create_project(db)
        first = make_draft(db, project_id)

        response = client.post(
            f"/api/v1/projects/{project_id}/drafts/from-version/{seed_version(db, project_id)}"
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "DRAFT_ALREADY_EXISTS"

        # The original draft is intact, not replaced by the rejected attempt.
        assert client.get(f"/api/v1/projects/{project_id}/draft").json()["id"] == first

    def test_a_failed_run_cannot_be_drafted(self, client, db):
        """A failed run's candidate is not publishable, so no draft is offered."""
        project_id = create_project(db)
        run_id = make_completed_run(db, project_id)
        run = db.get(GenerationRun, run_id)
        run.status = "failed"
        db.commit()

        response = client.post(f"/api/v1/projects/{project_id}/drafts/from-run/{run_id}")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CANDIDATE_NOT_AVAILABLE"

    def test_a_run_from_another_project_is_not_found(self, client, db):
        project_id = create_project(db, "Owner")
        other_id = create_project(db, "Other")
        run_id = make_completed_run(db, other_id)

        response = client.post(f"/api/v1/projects/{project_id}/drafts/from-run/{run_id}")
        assert response.status_code == 404

    def test_a_project_without_a_draft_reports_not_found(self, client, db):
        project_id = create_project(db)
        response = client.get(f"/api/v1/projects/{project_id}/draft")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "DRAFT_NOT_FOUND"


class TestPublicationReview:
    def test_preflight_is_read_only_and_agrees_with_publish_findings(self, client, db):
        project_id = create_project(db)
        artifact = load_fixture()
        concept = artifact["concepts"][0]
        concept["definition"] = concept["name"]
        draft_id = make_draft(db, project_id, artifact)
        before = client.get(f"/api/v1/projects/{project_id}/draft").json()

        response = client.get(f"/api/v1/drafts/{draft_id}/publish-check")
        assert response.status_code == 200, response.text
        review = response.json()
        assert any(
            issue["code"] == "CONCEPT_CIRCULAR_DEFINITION" for issue in review["concept_frame"]
        )
        assert client.get(f"/api/v1/projects/{project_id}/draft").json() == before
        assert list(db.scalars(select(COPVersion))) == []

        published = client.post(
            f"/api/v1/drafts/{draft_id}/publish",
            json={"reviewed_updated_at": review["updated_at"]},
        )
        assert published.status_code == 200, published.text
        for key in ("concept_frame", "content_gate", "unresolved_evidence"):
            assert (published.json()[key] or []) == review[key]

    def test_an_edit_after_preflight_requires_another_review(self, client, db):
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)
        review = client.get(f"/api/v1/drafts/{draft_id}/publish-check").json()
        concept_id = load_fixture()["concepts"][0]["id"]
        patched = client.patch(
            f"/api/v1/drafts/{draft_id}/concepts/{concept_id}",
            json={"definition": "Edited after reviewing this draft."},
        )
        assert patched.status_code == 200
        response = client.post(
            f"/api/v1/drafts/{draft_id}/publish",
            json={"reviewed_updated_at": review["updated_at"]},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "DRAFT_CHANGED"
        assert client.get(f"/api/v1/projects/{project_id}/draft").status_code == 200
        assert list(db.scalars(select(COPVersion))) == []

    def test_invalid_artifacts_cannot_receive_a_publish_preview(self, client, db):
        draft_id = make_draft(db, create_project(db), {"concepts": []})
        response = client.get(f"/api/v1/drafts/{draft_id}/publish-check")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "DRAFT_INVALID"


class TestManualEditing:
    def test_an_edit_survives_a_reload(self, client, db):
        """Acceptance: user edits survive refresh."""
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)
        goal_id = load_fixture()["goals"][0]["id"]

        patched = client.patch(
            f"/api/v1/drafts/{draft_id}/goals/{goal_id}",
            json={"outcome": "You can build a tool-calling agent from scratch."},
        )
        assert patched.status_code == 200, patched.text

        # A fresh GET, not the PATCH response, so this proves persistence.
        stored = client.get(f"/api/v1/projects/{project_id}/draft").json()["artifact"]
        goal = next(item for item in stored["goals"] if item["id"] == goal_id)
        assert goal["outcome"] == "You can build a tool-calling agent from scratch."

    def test_editing_one_goal_leaves_the_others_untouched(self, client, db):
        """A PATCH is a local correction, not a whole-artifact rewrite."""
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)
        fixture = load_fixture()
        first, second = fixture["goals"][0]["id"], fixture["goals"][1]["id"]

        client.patch(f"/api/v1/drafts/{draft_id}/goals/{first}", json={"title": "Renamed goal"})

        stored = client.get(f"/api/v1/projects/{project_id}/draft").json()["artifact"]
        by_id = {item["id"]: item for item in stored["goals"]}
        assert by_id[second] == fixture["goals"][1]

    def test_the_process_path_maps_to_the_main_process_entity(self, client, db):
        """Spec 24 §4: the API says /processes, the domain says MainProcess."""
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)
        process_id = load_fixture()["main_processes"][0]["id"]

        patched = client.patch(
            f"/api/v1/drafts/{draft_id}/processes/{process_id}",
            json={"outcome": "A working agent, end to end."},
        )
        assert patched.status_code == 200, patched.text
        stored = client.get(f"/api/v1/projects/{project_id}/draft").json()["artifact"]
        process = next(item for item in stored["main_processes"] if item["id"] == process_id)
        assert process["outcome"] == "A working agent, end to end."

    @pytest.mark.parametrize("segment", ["stages", "concepts", "operations"])
    def test_every_editable_entity_type_accepts_a_patch(self, client, db, segment):
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)
        collection = {
            "stages": ("stages", "title", "Edited stage title"),
            "concepts": ("concepts", "name", "Edited concept"),
            "operations": ("operations", "purpose", "Edited purpose"),
        }[segment]
        key, field, value = collection
        entity_id = load_fixture()[key][0]["id"]

        patched = client.patch(
            f"/api/v1/drafts/{draft_id}/{segment}/{entity_id}", json={field: value}
        )
        assert patched.status_code == 200, patched.text

    def test_artifact_metadata_is_editable(self, client, db):
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)

        patched = client.patch(
            f"/api/v1/drafts/{draft_id}/metadata", json={"summary": "How the system moves."}
        )
        assert patched.status_code == 200, patched.text
        stored = client.get(f"/api/v1/projects/{project_id}/draft").json()["artifact"]
        assert stored["mental_model"]["summary"] == "How the system moves."


class TestEditFencing:
    """Structural fields are the code's job, not the PATCH body's."""

    def test_reference_fields_cannot_be_rewritten(self, client, db):
        """A client must not be able to drop a Stage from the main line."""
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)
        process_id = load_fixture()["main_processes"][0]["id"]

        response = client.patch(
            f"/api/v1/drafts/{draft_id}/processes/{process_id}", json={"stage_refs": []}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "FIELD_NOT_EDITABLE"

        stored = client.get(f"/api/v1/projects/{project_id}/draft").json()["artifact"]
        process = next(item for item in stored["main_processes"] if item["id"] == process_id)
        assert process["stage_refs"], "stage_refs must be untouched"

    def test_an_entity_id_cannot_be_rewritten(self, client, db):
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)
        goal_id = load_fixture()["goals"][0]["id"]

        response = client.patch(
            f"/api/v1/drafts/{draft_id}/goals/{goal_id}", json={"id": "goal.hijacked"}
        )
        assert response.status_code == 422

    def test_a_required_field_cannot_be_emptied(self, client, db):
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)
        goal_id = load_fixture()["goals"][0]["id"]

        response = client.patch(
            f"/api/v1/drafts/{draft_id}/goals/{goal_id}", json={"outcome": "   "}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "FIELD_REQUIRED"

    def test_an_empty_edit_is_rejected(self, client, db):
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)
        goal_id = load_fixture()["goals"][0]["id"]

        assert (
            client.patch(f"/api/v1/drafts/{draft_id}/goals/{goal_id}", json={}).status_code == 422
        )

    def test_editing_an_absent_entity_reports_not_found(self, client, db):
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)

        response = client.patch(
            f"/api/v1/drafts/{draft_id}/goals/goal.does_not_exist", json={"title": "x"}
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ENTITY_NOT_FOUND"

    def test_an_oversized_field_is_rejected(self, client, db):
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)
        goal_id = load_fixture()["goals"][0]["id"]

        response = client.patch(
            f"/api/v1/drafts/{draft_id}/goals/{goal_id}", json={"title": "x" * 9000}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "FIELD_TOO_LONG"

    def test_a_rejected_edit_leaves_the_draft_byte_for_byte_unchanged(self, client, db):
        """Validation must happen before the write, not after."""
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)
        before = client.get(f"/api/v1/projects/{project_id}/draft").json()["artifact"]

        client.patch(
            f"/api/v1/drafts/{draft_id}/stages/{load_fixture()['stages'][0]['id']}",
            json={"local_goal": ""},
        )

        after = client.get(f"/api/v1/projects/{project_id}/draft").json()["artifact"]
        assert after == before


class TestPublish:
    def test_publishing_creates_version_one(self, client, db):
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)

        response = client.post(
            f"/api/v1/drafts/{draft_id}/publish", json={"change_summary": "First cut"}
        )
        assert response.status_code == 200, response.text
        version = response.json()
        assert version["version_number"] == 1
        assert version["parent_version_id"] is None
        assert version["created_by"] == "user"

    def test_v2_records_v1_as_its_parent(self, client, db):
        """Acceptance: v2 records parent v1."""
        project_id = create_project(db)
        first = seed_version(db, project_id)

        draft_id = make_draft(db, project_id)
        second = client.post(f"/api/v1/drafts/{draft_id}/publish", json={}).json()

        assert second["version_number"] == 2
        assert second["parent_version_id"] == first

    def test_a_draft_forked_from_an_old_version_keeps_that_parent(self, client, db):
        project_id = create_project(db)
        first = seed_version(db, project_id)
        draft_id = make_draft(db, project_id)
        client.post(f"/api/v1/drafts/{draft_id}/publish", json={})

        fork = client.post(f"/api/v1/projects/{project_id}/drafts/from-version/{first}").json()
        third = client.post(f"/api/v1/drafts/{fork['id']}/publish", json={}).json()

        assert third["version_number"] == 3
        assert third["parent_version_id"] == first

    def test_publishing_clears_the_active_draft(self, client, db):
        """Otherwise the draft would shadow the version just published."""
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)

        client.post(f"/api/v1/drafts/{draft_id}/publish", json={})

        assert client.get(f"/api/v1/projects/{project_id}/draft").status_code == 404
        assert db.get(Draft, draft_id) is None

    def test_the_published_artifact_contains_the_users_edits(self, client, db):
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)
        goal_id = load_fixture()["goals"][0]["id"]
        client.patch(
            f"/api/v1/drafts/{draft_id}/goals/{goal_id}", json={"title": "Published title"}
        )

        version = client.post(f"/api/v1/drafts/{draft_id}/publish", json={}).json()
        stored = client.get(f"/api/v1/versions/{version['id']}").json()
        goal = next(item for item in stored["artifact"]["goals"] if item["id"] == goal_id)
        assert goal["title"] == "Published title"

    def test_publishing_a_draft_with_a_broken_artifact_is_refused(self, client, db):
        """A draft can only be corrupted by direct DB access, but publishing is
        still the last place to catch it."""
        project_id = create_project(db)
        draft_id = make_draft(db, project_id)
        draft = db.get(Draft, draft_id)
        broken = load_fixture()
        broken["main_processes"][0]["stage_refs"] = ["stage.does_not_exist"]
        draft.artifact_json = broken
        db.commit()

        response = client.post(f"/api/v1/drafts/{draft_id}/publish", json={})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "DRAFT_INVALID"
        assert db.scalar(select(COPVersion).where(COPVersion.project_id == project_id)) is None

    def test_a_draft_must_be_published_before_another_can_exist(self, client, db):
        project_id = create_project(db)
        run_id = make_completed_run(db, project_id)
        client.post(f"/api/v1/projects/{project_id}/drafts/from-run/{run_id}")
        draft_id = client.get(f"/api/v1/projects/{project_id}/draft").json()["id"]
        client.post(f"/api/v1/drafts/{draft_id}/publish", json={})

        response = client.post(f"/api/v1/projects/{project_id}/drafts/from-run/{run_id}")
        assert response.status_code == 201


class TestVersionImmutability:
    def test_no_endpoint_can_mutate_a_published_version(self, client, db):
        """Acceptance: a published version cannot be changed.

        Asserted against the OpenAPI document rather than by calling an endpoint
        that should not exist, so the guarantee holds even if someone re-adds
        one. Reading the schema rather than `app.routes` also avoids depending on
        how the router happens to be mounted.
        """
        mutating = {"post", "patch", "put", "delete"}
        published_version_writes = [
            f"{method.upper()} {path}"
            for path, operations in client.get("/openapi.json").json()["paths"].items()
            for method in operations
            if method in mutating
            and "/versions" in path
            and "/versions/latest" not in path
            and not path.endswith("/exports")
        ]
        assert published_version_writes == [], (
            f"published versions must stay immutable, found: {published_version_writes}"
        )

    def test_draft_writes_are_the_only_mutating_artifact_endpoints(self, client, db):
        """Guards the opposite direction: the draft API is not accidentally inert."""
        paths = client.get("/openapi.json").json()["paths"]
        assert "patch" in paths["/api/v1/drafts/{draft_id}/{entity_type}/{entity_id}"]
        assert "post" in paths["/api/v1/drafts/{draft_id}/publish"]
        assert "delete" in paths["/api/v1/drafts/{draft_id}"]

    def test_a_published_version_is_unchanged_by_later_draft_work(self, client, db):
        project_id = create_project(db)
        version_id = seed_version(db, project_id)
        before = client.get(f"/api/v1/versions/{version_id}").json()

        draft_id = make_draft(db, project_id)
        goal_id = load_fixture()["goals"][0]["id"]
        client.patch(f"/api/v1/drafts/{draft_id}/goals/{goal_id}", json={"title": "Diverged"})
        client.post(f"/api/v1/drafts/{draft_id}/publish", json={})

        after = client.get(f"/api/v1/versions/{version_id}").json()
        assert after == before

    def test_discarding_a_draft_leaves_versions_alone(self, client, db):
        project_id = create_project(db)
        version_id = seed_version(db, project_id)
        before = client.get(f"/api/v1/versions/{version_id}").json()
        draft_id = make_draft(db, project_id)

        assert client.delete(f"/api/v1/drafts/{draft_id}").status_code == 204

        assert db.get(Draft, draft_id) is None
        assert client.get(f"/api/v1/versions/{version_id}").json() == before

    def test_the_version_list_reports_newest_first_with_provenance(self, client, db):
        project_id = create_project(db)
        first = seed_version(db, project_id)
        draft_id = make_draft(db, project_id)
        client.post(f"/api/v1/drafts/{draft_id}/publish", json={})

        versions = client.get(f"/api/v1/projects/{project_id}/versions").json()
        assert [item["version_number"] for item in versions] == [2, 1]
        assert versions[0]["parent_version_id"] == first
        assert versions[1]["parent_version_id"] is None
