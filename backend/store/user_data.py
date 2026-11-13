"""Portable archives for liked images, feedback, and learned preferences."""
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import tempfile
import uuid
import zipfile

from ..domain import ConflictError, ValidationError
from ..recommendation import policy
from ..recommendation.contracts import PolicyRecord
from .assets import EXTENSIONS, local_image
from .recommendation import _decode as decode_candidate


FORMAT = "pictide-user-data"
FORMAT_VERSION = 1
MAX_ARCHIVE_BYTES = 4 * 1024**3
MAX_EXPANDED_BYTES = 8 * 1024**3
MAX_DATA_BYTES = 128 * 1024**2
MAX_POLICY_BYTES = 1024**3
MAX_ITEMS = 100_000
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,100}")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _timestamp(value, label):
    if not isinstance(value, str) or len(value) > 64:
        raise ValidationError(f"{label} is invalid.")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError(f"{label} is invalid.") from None
    return value


def _identifier(value, label):
    if not isinstance(value, str) or IDENTIFIER.fullmatch(value) is None:
        raise ValidationError(f"{label} is invalid.")
    return value


def _integer(value, label, minimum=0, maximum=2**53 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValidationError(f"{label} is invalid.")
    return value


def _member(name):
    if not isinstance(name, str) or "\\" in name or name.startswith("/"):
        raise ValidationError("The user-data archive contains an invalid path.")
    path = PurePosixPath(name)
    if not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ValidationError("The user-data archive contains an invalid path.")
    if path.parts[0] not in {"manifest.json", "data.json", "images", "prompts", "state"}:
        raise ValidationError("The user-data archive contains an unsupported file.")
    return path.as_posix()


def _write_bytes(archive, name, content, files, compression=zipfile.ZIP_DEFLATED):
    files.append({"path": name, "size": len(content), "sha256": _digest(content)})
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = compression
    info.external_attr = 0o600 << 16
    archive.writestr(info, content)


def _write_file(archive, name, path, files):
    digest = hashlib.sha256()
    size = 0
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o600 << 16
    with path.open("rb") as source, archive.open(info, "w") as target:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
            target.write(chunk)
    files.append({"path": name, "size": size, "sha256": digest.hexdigest()})


def _candidate(value):
    try:
        candidate = decode_candidate(_json(value))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise ValidationError("The user-data archive contains invalid recommendation evidence.") from None
    return json.dumps({
        "candidate_id": candidate.candidate_id,
        "positive": candidate.positive,
        "negative": candidate.negative,
        "terms": [{"text": term.text, "channel": term.channel} for term in candidate.terms],
    }, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _recommendation_snapshot(db, feature_version):
    policy_row = db.execute(
        "SELECT * FROM recommendation_policy WHERE user_id='local' AND feature_version=?",
        (feature_version,)).fetchone()
    evidence = db.execute(
        "SELECT artifact_id,revision,value,candidate FROM recommendation_evidence "
        "WHERE user_id='local' AND feature_version=? ORDER BY revision",
        (feature_version,)).fetchall()
    # Restore needs the latest event for each artifact plus the exact revisions
    # referenced by evidence. Older journal entries are not transferable state.
    events = db.execute("""
        SELECT e.revision,e.artifact_id,e.value,e.candidate
        FROM recommendation_events e
        WHERE e.user_id='local' AND (
            e.revision IN (SELECT revision FROM recommendation_evidence
                           WHERE user_id='local' AND feature_version=?)
            OR e.revision = (SELECT MAX(newer.revision)
                             FROM recommendation_events newer
                             WHERE newer.user_id=e.user_id
                               AND newer.artifact_id=e.artifact_id))
        ORDER BY e.revision""", (feature_version,)).fetchall()
    reset = db.execute("SELECT revision,event_floor,reset_at FROM recommendation_resets "
                       "WHERE user_id='local'").fetchone()
    score_range = db.execute(
        "SELECT score_min,score_max FROM recommendation_score_range "
        "WHERE user_id='local' AND feature_version=? AND policy_version=?",
        (feature_version, policy.POLICY_VERSION)).fetchone()
    try:
        result = {
            "feature_version": feature_version,
            "policy_version": policy.POLICY_VERSION,
            "policy": ({
                "revision": policy_row["revision"],
                "term_keys": json.loads(policy_row["term_keys"]),
                "precision": base64.b64encode(policy_row["precision"]).decode("ascii"),
                "reward": base64.b64encode(policy_row["reward"]).decode("ascii"),
                "evidence_count": policy_row["evidence_count"],
            } if policy_row else None),
            "events": [{
                "revision": row["revision"],
                "artifact_id": row["artifact_id"],
                "value": row["value"],
                "candidate": json.loads(row["candidate"]),
            } for row in events],
            "evidence": [{
                "artifact_id": row["artifact_id"],
                "revision": row["revision"],
                "value": row["value"],
                "candidate": json.loads(row["candidate"]),
            } for row in evidence],
            "reset": ({
                "revision": reset["revision"],
                # The compact journal contains only current evidence and the
                # latest event per artifact, so pre-reset history is absent.
                "event_floor": 0,
                "reset_at": reset["reset_at"],
            } if reset else None),
            "score_range": ({
                "min": score_range["score_min"],
                "max": score_range["score_max"],
            } if score_range else None),
        }
    except (ValueError, TypeError, json.JSONDecodeError):
        raise ValidationError("The learned preference state cannot be exported.") from None
    return result


def export_user_data(paths, storage, app_version, feature_version, policy_version,
                     *, include_liked=True, include_preferences=True):
    """Build a temporary ZIP from one coherent database read and liked originals."""
    if not include_liked and not include_preferences:
        raise ValidationError("Select at least one user-data category to export.")
    with storage.connection() as db:
        db.execute("BEGIN")
        rows = db.execute("""
            SELECT a.id,a.node_id,a.output_index,a.created_at,a.local_path,a.content_type,
                   j.id AS job_id,j.request_id,j.positive,j.negative,j.prompt_snapshot,j.seed,
                   j.width,j.height,f.updated_at AS feedback_updated_at,
                   CASE WHEN EXISTS (SELECT 1 FROM roam_jobs r WHERE r.job_id=j.id)
                        THEN 'roam' ELSE 'generate' END AS source,
                   COALESCE(json_extract(b.config,'$.kind'),'comfyui') AS backend_kind,
                   json_type(b.config,'$.bindings.seed')='object' AS seed_applied,
                   (SELECT candidate FROM roam_jobs r WHERE r.job_id=j.id LIMIT 1) AS source_candidate
            FROM feedback f JOIN artifacts a ON a.id=f.artifact_id
            JOIN jobs j ON j.id=a.job_id JOIN backend_revisions b ON b.id=j.revision_id
            WHERE f.actor_id='local' AND f.value=1 AND a.deleted_at IS NULL
            ORDER BY a.created_at,a.id""").fetchall() if include_liked else []
        recommendation = _recommendation_snapshot(db, feature_version) if include_preferences else None
        liked, images = [], []
        for row in rows:
            identifier = _identifier(row["id"], "Liked image ID")
            source = local_image(paths, row["local_path"])
            if source is None:
                raise ValidationError(f"Liked image {identifier} is missing from the data directory.")
            extension = EXTENSIONS.get(row["content_type"])
            if extension is None:
                raise ValidationError(f"Liked image {identifier} has an unsupported content type.")
            image_member = f"images/{identifier}{extension}"
            prompt_member = f"prompts/{identifier}.json"
            snapshot = json.loads(row["prompt_snapshot"]) if row["prompt_snapshot"] else None
            source_candidate = json.loads(row["source_candidate"]) if row["source_candidate"] else None
            feedback_updated_at = row["feedback_updated_at"] or row["created_at"]
            liked.append({
                "artifact": {
                    "id": identifier,
                    "node_id": row["node_id"],
                    "output_index": row["output_index"],
                    "created_at": _timestamp(row["created_at"], "Image creation time"),
                    "content_type": row["content_type"],
                    "source": row["source"],
                },
                "job": {
                    "id": _identifier(row["job_id"], "Job ID"),
                    "request_id": row["request_id"],
                    "positive": row["positive"],
                    "negative": row["negative"],
                    "prompt_snapshot": snapshot,
                    "seed": row["seed"],
                    "width": row["width"],
                    "height": row["height"],
                    "backend_kind": row["backend_kind"],
                    "seed_applied": bool(row["seed_applied"]),
                },
                "feedback": {
                    "value": 1,
                    "updated_at": _timestamp(feedback_updated_at, "Feedback time"),
                },
                "source_candidate": source_candidate,
                "image": image_member,
                "prompts": prompt_member,
            })
            images.append((image_member, prompt_member, source, liked[-1]))

    document = {
        "format_version": FORMAT_VERSION,
        "categories": {
            "liked_images": include_liked,
            "preferences": include_preferences,
        },
        "liked": liked,
        "recommendation": recommendation,
    }
    for item in liked:
        _validate_liked(item)
    if include_preferences:
        _validate_recommendation(document, feature_version, policy_version)
    state_files = []
    state = recommendation["policy"] if recommendation is not None else None
    if state is not None:
        precision = base64.b64decode(state.pop("precision"))
        reward = base64.b64decode(state.pop("reward"))
        state["precision_file"] = "state/precision.bin"
        state["reward_file"] = "state/reward.bin"
        state_files = [
            ("state/precision.bin", precision),
            ("state/reward.bin", reward),
        ]
    data = _json(document).encode("utf-8")
    if len(liked) > MAX_ITEMS:
        raise ValidationError("There are too many liked images to export in one user-data archive.")
    if len(data) > MAX_DATA_BYTES:
        raise ValidationError("The learned preference state is too large to export in one user-data archive.")
    created_at = datetime.now(timezone.utc).isoformat()
    files = []
    descriptor, temporary = tempfile.mkstemp(prefix="user-data-", suffix=".zip", dir=paths.tmp)
    os.close(descriptor)
    temporary = Path(temporary)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            _write_bytes(archive, "data.json", data, files)
            for name, content in state_files:
                _write_bytes(archive, name, content, files, compression=zipfile.ZIP_STORED)
            for image_member, prompt_member, source, item in images:
                _write_file(archive, image_member, source, files)
                prompt = _json({
                    "positive": item["job"]["positive"],
                    "negative": item["job"]["negative"],
                }).encode("utf-8")
                _write_bytes(archive, prompt_member, prompt, files)
            manifest = {
                "format": FORMAT,
                "format_version": FORMAT_VERSION,
                "app_version": app_version,
                "created_at": created_at,
                "feature_version": feature_version,
                "policy_version": policy_version,
                "categories": {
                    "liked_images": include_liked,
                    "preferences": include_preferences,
                },
                "counts": {
                    "liked_images": len(liked),
                    "feedback": len(liked),
                    "recommendation_events": len(recommendation["events"]) if recommendation else 0,
                    "recommendation_evidence": len(recommendation["evidence"]) if recommendation else 0,
                },
                "files": files,
            }
            _write_bytes(archive, "manifest.json", _json(manifest).encode("utf-8"), [])
        if sum(entry["size"] for entry in files) > MAX_EXPANDED_BYTES:
            raise ValidationError("The user-data archive is too large when expanded.")
        if temporary.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValidationError("The user-data archive is too large to import later.")
        return temporary, f"pictide-user-data-{created_at[:19].replace('-', '').replace(':', '')}.zip"
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _archive_categories(manifest, data):
    categories = manifest.get("categories")
    if categories is None:
        # Version-1 archives created before selective export always contained both.
        return {"liked_images": True, "preferences": True}
    if (not isinstance(categories, dict)
            or set(categories) != {"liked_images", "preferences"}
            or any(type(categories[key]) is not bool for key in categories)
            or not any(categories.values())):
        raise ValidationError("The user-data archive has invalid category selection.")
    declared = data.get("categories")
    if declared is not None and declared != categories:
        raise ValidationError("The user-data archive categories are inconsistent.")
    return categories


def _verify_archive(archive, manifest, data, names):
    if manifest.get("format") != FORMAT or manifest.get("format_version") != FORMAT_VERSION:
        raise ValidationError("This is not a supported Pictide user-data archive.")
    if (not isinstance(manifest.get("app_version"), str) or len(manifest["app_version"]) > 100
            or not isinstance(manifest.get("created_at"), str)):
        raise ValidationError("The user-data manifest is incomplete.")
    _timestamp(manifest["created_at"], "Archive creation time")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValidationError("The user-data manifest is incomplete.")
    declared = {}
    expanded = 0
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}:
            raise ValidationError("The user-data manifest is invalid.")
        name = _member(entry["path"])
        if name in declared or name not in names or name == "manifest.json":
            raise ValidationError("The user-data manifest contains duplicate or unsupported files.")
        size = _integer(entry["size"], "Archived file size")
        digest = entry["sha256"]
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValidationError("The user-data manifest contains an invalid checksum.")
        expanded += size
        if expanded > MAX_EXPANDED_BYTES:
            raise ValidationError("The user-data archive is too large when expanded.")
        declared[name] = (size, digest)
    if set(names) - {"manifest.json"} != set(declared):
        raise ValidationError("The user-data archive contains files not listed in its manifest.")
    for name, (size, digest) in declared.items():
        actual = hashlib.sha256()
        actual_size = 0
        with archive.open(name) as stream:
            while chunk := stream.read(1024 * 1024):
                actual_size += len(chunk)
                actual.update(chunk)
        if actual_size != size or actual.hexdigest() != digest:
            raise ValidationError(f"User-data archive checksum mismatch for {name}.")
    categories = _archive_categories(manifest, data)
    liked = data.get("liked")
    if not isinstance(liked, list) or len(liked) > MAX_ITEMS:
        raise ValidationError("The user-data archive has an invalid liked-image list.")
    expected = {"data.json"}
    identifiers = set()
    for item in liked:
        if not isinstance(item, dict):
            raise ValidationError("The user-data archive has an invalid liked image.")
        artifact = item.get("artifact")
        if not isinstance(artifact, dict):
            raise ValidationError("The user-data archive has an invalid liked image.")
        identifier = _identifier(artifact.get("id"), "Liked image ID")
        if identifier in identifiers:
            raise ValidationError("The user-data archive has duplicate liked-image identifiers.")
        identifiers.add(identifier)
        expected.add(_member(item.get("image")))
        expected.add(_member(item.get("prompts")))
        if item["image"] != f"images/{identifier}{Path(item['image']).suffix}":
            raise ValidationError("The user-data archive has an invalid image filename.")
        if item["prompts"] != f"prompts/{identifier}.json":
            raise ValidationError("The user-data archive has an invalid prompt filename.")
        _validate_liked(item)
    if not categories["liked_images"] and liked:
        raise ValidationError("The user-data archive contains unselected liked images.")
    recommendation = data.get("recommendation")
    if not categories["preferences"] and recommendation is not None:
        raise ValidationError("The user-data archive contains unselected preference data.")
    state = recommendation.get("policy") if isinstance(recommendation, dict) else None
    if isinstance(state, dict):
        for key in ("precision", "reward"):
            member = state.get(f"{key}_file")
            if member is not None:
                expected.add(_member(member))
    if {name for name in declared if name != "data.json"} != expected - {"data.json"}:
        raise ValidationError("The user-data archive has unreferenced files.")


def _validate_liked(item):
    artifact, job, feedback = item.get("artifact"), item.get("job"), item.get("feedback")
    if not isinstance(artifact, dict) or not isinstance(job, dict) or not isinstance(feedback, dict):
        raise ValidationError("The user-data archive has incomplete liked-image data.")
    _identifier(artifact.get("id"), "Liked image ID")
    _identifier(job.get("id"), "Job ID")
    if not isinstance(artifact.get("node_id"), str) or len(artifact["node_id"]) > 100:
        raise ValidationError("The user-data archive has an invalid image node.")
    _integer(artifact.get("output_index"), "Image output index")
    _timestamp(artifact.get("created_at"), "Image creation time")
    content_type = artifact.get("content_type")
    if content_type not in EXTENSIONS:
        raise ValidationError("The user-data archive has an unsupported image type.")
    if Path(item["image"]).suffix != EXTENSIONS[content_type]:
        raise ValidationError("The user-data archive has inconsistent image metadata.")
    if artifact.get("source") not in ("roam", "generate"):
        raise ValidationError("The user-data archive has an invalid image source.")
    for key in ("positive", "negative"):
        if not isinstance(job.get(key), str):
            raise ValidationError("The user-data archive has invalid prompt text.")
    if job.get("prompt_snapshot") is not None and not isinstance(job["prompt_snapshot"], dict):
        raise ValidationError("The user-data archive has an invalid prompt snapshot.")
    _integer(job.get("seed"), "Image seed")
    for key in ("width", "height"):
        if job.get(key) is not None:
            _integer(job[key], f"Image {key}", 1, 16384)
    if not isinstance(job.get("backend_kind"), str) or len(job["backend_kind"]) > 100:
        raise ValidationError("The user-data archive has an invalid backend kind.")
    if type(job.get("seed_applied")) is not bool:
        raise ValidationError("The user-data archive has invalid seed metadata.")
    if feedback.get("value") != 1:
        raise ValidationError("Only currently liked images can be imported.")
    _timestamp(feedback.get("updated_at"), "Feedback time")
    if item.get("source_candidate") is not None:
        if not isinstance(item["source_candidate"], dict):
            raise ValidationError("The user-data archive has an invalid source prompt.")


def _validate_recommendation(data, feature_version, current_policy_version):
    recommendation = data.get("recommendation")
    if not isinstance(recommendation, dict):
        raise ValidationError("The user-data archive has no preference state.")
    if recommendation.get("feature_version") != feature_version:
        raise ValidationError("This user-data archive was created with an incompatible recommendation feature version.")
    if recommendation.get("policy_version") != current_policy_version:
        raise ValidationError("This user-data archive was created with an incompatible preference policy.")
    events = recommendation.get("events")
    evidence = recommendation.get("evidence")
    if not isinstance(events, list) or len(events) > MAX_ITEMS or not isinstance(evidence, list) or len(evidence) > MAX_ITEMS:
        raise ValidationError("The user-data archive has invalid recommendation records.")
    event_revisions = set()
    for event in events:
        if not isinstance(event, dict):
            raise ValidationError("The user-data archive has invalid recommendation events.")
        revision = _integer(event.get("revision"), "Recommendation revision", 1)
        if revision in event_revisions:
            raise ValidationError("The user-data archive has duplicate recommendation revisions.")
        event_revisions.add(revision)
        _identifier(event.get("artifact_id"), "Recommendation artifact ID")
        if event.get("value") not in (-1, 1, None):
            raise ValidationError("The user-data archive has an invalid recommendation value.")
        _candidate(event.get("candidate"))
    active = 0
    evidence_artifacts = set()
    for row in evidence:
        if not isinstance(row, dict):
            raise ValidationError("The user-data archive has invalid recommendation evidence.")
        revision = _integer(row.get("revision"), "Recommendation revision", 1)
        if revision not in event_revisions:
            raise ValidationError("The user-data archive has recommendation evidence without its event.")
        artifact_id = _identifier(row.get("artifact_id"), "Recommendation artifact ID")
        if artifact_id in evidence_artifacts:
            raise ValidationError("The user-data archive has duplicate recommendation evidence.")
        evidence_artifacts.add(artifact_id)
        if row.get("value") not in (-1, 1, None):
            raise ValidationError("The user-data archive has an invalid recommendation value.")
        _candidate(row.get("candidate"))
        active += row.get("value") is not None
    state = recommendation.get("policy")
    if state is not None:
        if not isinstance(state, dict):
            raise ValidationError("The user-data archive has an invalid preference state.")
        revision = _integer(state.get("revision"), "Preference revision")
        keys = state.get("term_keys")
        if not isinstance(keys, list) or len(keys) != len(set(keys)) or not all(isinstance(key, str) for key in keys):
            raise ValidationError("The user-data archive has invalid learned terms.")
        try:
            precision = base64.b64decode(state.get("precision"), validate=True)
            reward = base64.b64decode(state.get("reward"), validate=True)
            policy.unpack(PolicyRecord(revision, tuple(keys), precision, reward,
                                       _integer(state.get("evidence_count"), "Evidence count")))
        except (ValueError, TypeError):
            raise ValidationError("The user-data archive has an invalid preference matrix.") from None
        if state["evidence_count"] != active:
            raise ValidationError("The user-data archive has inconsistent preference evidence.")
    reset = recommendation.get("reset")
    if reset is not None:
        if not isinstance(reset, dict):
            raise ValidationError("The user-data archive has an invalid reset state.")
        _integer(reset.get("revision"), "Reset revision", 1)
        floor = _integer(reset.get("event_floor"), "Reset event floor")
        _timestamp(reset.get("reset_at"), "Reset time")
    score_range = recommendation.get("score_range")
    if score_range is not None:
        if not isinstance(score_range, dict):
            raise ValidationError("The user-data archive has an invalid score range.")
        if any(type(score_range.get(key)) not in (int, float) or not math.isfinite(score_range[key])
               for key in ("min", "max")) or score_range["min"] > score_range["max"]:
            raise ValidationError("The user-data archive has an invalid score range.")
    return recommendation


def _backup_database(paths):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    target = paths.root / "backups" / f"before-user-data-import-{stamp}" / "pictide.sqlite3"
    target.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(paths.database)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return target.relative_to(paths.root).as_posix()


def _read_json(archive, name, limit):
    info = archive.getinfo(name)
    if info.file_size > limit:
        raise ValidationError("The user-data archive contains an oversized JSON file.")
    try:
        return json.loads(archive.read(name).decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError):
        raise ValidationError("The user-data archive contains invalid JSON.") from None


def _hydrate_policy_state(archive, data):
    recommendation = data.get("recommendation")
    state = recommendation.get("policy") if isinstance(recommendation, dict) else None
    if not isinstance(state, dict):
        return
    for key in ("precision", "reward"):
        if key in state:
            continue
        member = state.get(f"{key}_file")
        if member is None:
            continue
        member = _member(member)
        if archive.getinfo(member).file_size > MAX_POLICY_BYTES:
            raise ValidationError("The user-data archive contains an oversized preference matrix.")
        state[key] = base64.b64encode(archive.read(member)).decode("ascii")


def _extract(archive, member, target, paths, expected):
    descriptor, temporary = tempfile.mkstemp(prefix="user-data-import-", suffix=".part", dir=paths.tmp)
    temporary = Path(temporary)
    digest = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(descriptor, "wb") as stream, archive.open(member) as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
                stream.write(chunk)
        if size != expected["size"] or digest.hexdigest() != expected["sha256"]:
            raise ValidationError(f"User-data archive checksum mismatch for {member}.")
        created = not target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(target)
        return created
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _prepare_files(archive, data, manifest, paths, identifiers):
    declared = {entry["path"]: entry for entry in manifest["files"]}
    created = []
    prepared = []
    skipped = 0
    try:
        for item in data["liked"]:
            identifier = item["artifact"]["id"]
            if identifier in identifiers:
                skipped += 1
                continue
            image_member, prompt_member = item["image"], item["prompts"]
            extension = Path(image_member).suffix
            image = paths.images / f"import-{identifier}-{declared[image_member]['sha256'][:12]}{extension}"
            prompts = image.with_suffix(".json")
            if _extract(archive, image_member, image, paths, declared[image_member]):
                created.append(image)
            if _extract(archive, prompt_member, prompts, paths, declared[prompt_member]):
                created.append(prompts)
            prepared.append((item, image.relative_to(paths.root).as_posix()))
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return prepared, created, skipped


def _import_database(storage, prepared, recommendation, *, import_preferences=True,
                     migrate_preferences=False):
    imported = skipped = 0
    with storage.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        for item, local_path in prepared:
            artifact = item["artifact"]
            identifier = artifact["id"]
            if db.execute("SELECT 1 FROM artifacts WHERE id=?", (identifier,)).fetchone():
                skipped += 1
                continue
            job = item["job"]
            existing = db.execute(
                "SELECT revision_id,positive,negative,seed,width,height,prompt_snapshot "
                "FROM jobs WHERE id=?", (job["id"],)).fetchone()
            if existing:
                revision_id = existing["revision_id"]
                snapshot = (_json(json.loads(existing["prompt_snapshot"]))
                            if existing["prompt_snapshot"] is not None else None)
                expected_snapshot = (_json(job["prompt_snapshot"])
                                     if job["prompt_snapshot"] is not None else None)
                if (existing["positive"], existing["negative"], existing["seed"],
                        existing["width"], existing["height"], snapshot) != (
                        job["positive"], job["negative"], job["seed"],
                        job["width"], job["height"], expected_snapshot):
                    raise ValidationError("The user-data archive conflicts with an existing generation task.")
            else:
                revision_id = "import-" + uuid.uuid4().hex
                configuration = {
                    "id": job["id"],
                    "name": "Imported",
                    "kind": job["backend_kind"],
                    "base_url": "",
                    "api_key": "",
                    "workflow": {},
                    "bindings": ({"seed": {"node_id": "imported", "input": "seed"}}
                                 if job["seed_applied"] else {}),
                }
                db.execute("INSERT INTO backend_revisions VALUES (?,?,?,?)",
                           (revision_id, job["id"], _json(configuration), artifact["created_at"]))
                request_id = job["request_id"] if isinstance(job["request_id"], str) and job["request_id"] else uuid.uuid4().hex
                if db.execute("SELECT 1 FROM jobs WHERE request_id=?", (request_id,)).fetchone():
                    request_id = "import-" + uuid.uuid4().hex
                payload_hash = hashlib.sha256(_json(job).encode("utf-8")).hexdigest()
                db.execute("""
                    INSERT INTO jobs
                    (id,request_id,payload_hash,backend_id,revision_id,status,positive,negative,seed,
                     backend_prompt_id,error,backend_pending,created_at,updated_at,prompt_snapshot,width,height)
                    VALUES (?,?,?,?,?,'completed',?,?,?,NULL,NULL,0,?,?,?,?,?)""",
                    (job["id"], request_id, payload_hash, job["id"], revision_id, job["positive"],
                     job["negative"], job["seed"], artifact["created_at"], artifact["created_at"],
                     _json(job["prompt_snapshot"]) if job["prompt_snapshot"] is not None else None,
                     job["width"], job["height"]))
            descriptor = {"filename": Path(local_path).name, "content_type": artifact["content_type"]}
            db.execute("""
                INSERT INTO artifacts
                (id,job_id,node_id,output_index,descriptor,created_at,local_path,content_type,
                 deleted_at,generated_hidden_at,roam_hidden_at,unliked_protected_until)
                VALUES (?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL)""",
                (identifier, job["id"], artifact["node_id"], artifact["output_index"],
                 _json(descriptor), artifact["created_at"], local_path, artifact["content_type"]))
            if artifact["source"] == "roam":
                candidate = item.get("source_candidate") or {
                    "candidate_id": "", "positive": job["positive"], "negative": job["negative"], "terms": []}
                db.execute("INSERT OR IGNORE INTO roam_jobs(job_id,epoch,candidate,created_at) VALUES (?,?,?,?)",
                           (job["id"], "import-" + uuid.uuid4().hex, _json(candidate), artifact["created_at"]))
            db.execute("INSERT INTO feedback VALUES (?,'local',1,?) "
                       "ON CONFLICT(artifact_id,actor_id) DO UPDATE SET value=1,updated_at=excluded.updated_at",
                       (identifier, item["feedback"]["updated_at"]))
            imported += 1

        if import_preferences:
            db.execute("DELETE FROM recommendation_policy WHERE user_id='local'")
            db.execute("DELETE FROM recommendation_events WHERE user_id='local'")
            db.execute("DELETE FROM recommendation_evidence WHERE user_id='local'")
            db.execute("DELETE FROM recommendation_resets WHERE user_id='local'")
            db.execute("DELETE FROM recommendation_reset_requests WHERE user_id='local'")
            db.execute("DELETE FROM recommendation_learning_boundaries WHERE user_id='local'")
            db.execute("DELETE FROM recommendation_score_range WHERE user_id='local'")
            db.execute("DELETE FROM artifact_preference_scores")
            revision_map = {}
            for event in recommendation["events"]:
                cursor = db.execute(
                    "INSERT INTO recommendation_events(user_id,artifact_id,value,candidate) VALUES ('local',?,?,?)",
                    (event["artifact_id"], event["value"], _candidate(event["candidate"])))
                revision_map[event["revision"]] = cursor.lastrowid
            if not migrate_preferences:
                for row in recommendation["evidence"]:
                    revision = revision_map.get(row["revision"])
                    if revision is None:
                        raise ValidationError("The user-data archive has recommendation evidence without its event.")
                    db.execute("INSERT INTO recommendation_evidence VALUES ('local',?,?,?,?,?)",
                               (recommendation["feature_version"], row["artifact_id"], revision, row["value"],
                                _candidate(row["candidate"])))
                state = recommendation["policy"]
                if state is not None:
                    db.execute("INSERT INTO recommendation_policy VALUES ('local',?,?,?,?,?,?)",
                               (recommendation["feature_version"], state["revision"], _json(state["term_keys"]),
                                base64.b64decode(state["precision"]), base64.b64decode(state["reward"]),
                                state["evidence_count"]))
            reset = recommendation["reset"]
            if reset is not None:
                floor = revision_map.get(reset["event_floor"])
                if floor is None and reset["event_floor"] != 0:
                    floor = max(revision_map.values(), default=0)
                db.execute("INSERT INTO recommendation_resets VALUES ('local',?,?,?)",
                           (reset["revision"], floor or 0, reset["reset_at"]))
            if not migrate_preferences:
                boundary = max(revision_map.values(), default=0)
                db.execute("INSERT INTO recommendation_learning_boundaries VALUES ('local',?,?)",
                           (boundary, datetime.now(timezone.utc).isoformat()))
            score_range = recommendation["score_range"]
            if score_range is not None and not migrate_preferences:
                db.execute("INSERT INTO recommendation_score_range VALUES ('local',?,?,?,?)",
                           (recommendation["feature_version"], recommendation["policy_version"],
                            score_range["min"], score_range["max"]))
    return imported, skipped


def import_user_data(paths, storage, archive_path, feature_version, policy_version):
    """Validate a complete archive, back up the current database, then merge it."""
    archive_path = Path(archive_path)
    if not archive_path.is_file() or archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValidationError("The user-data archive is missing or too large.")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ITEMS * 2 + 2:
                raise ValidationError("The user-data archive contains too many files.")
            names = [_member(info.filename) for info in infos]
            if len(names) != len(set(names)) or "manifest.json" not in names or "data.json" not in names:
                raise ValidationError("The user-data archive is incomplete or contains duplicate files.")
            manifest = _read_json(archive, "manifest.json", 1024 * 1024)
            data = _read_json(archive, "data.json", MAX_DATA_BYTES)
            if not isinstance(manifest, dict) or not isinstance(data, dict) or data.get("format_version") != FORMAT_VERSION:
                raise ValidationError("The user-data archive has an invalid manifest or data document.")
            archive_feature = manifest.get("feature_version")
            _verify_archive(archive, manifest, data, names)
            categories = _archive_categories(manifest, data)
            recommendation = None
            migrate_preferences = False
            if categories["preferences"]:
                if not isinstance(archive_feature, str) or manifest.get("policy_version") != policy_version:
                    raise ValidationError("This user-data archive uses an incompatible preference policy.")
                migrate_preferences = archive_feature != feature_version
                _hydrate_policy_state(archive, data)
                recommendation = _validate_recommendation(data, archive_feature, policy_version)
            with storage.connection() as db:
                identifiers = {row["id"] for row in db.execute("SELECT id FROM artifacts")}
                if db.execute("SELECT 1 FROM jobs WHERE status IN "
                              "('queued','submitting','running') LIMIT 1").fetchone():
                    raise ConflictError("Finish running or queued generation tasks before importing user data.")
            backup = _backup_database(paths)
            prepared, created, skipped_existing = _prepare_files(
                archive, data, manifest, paths, identifiers) if categories["liked_images"] else ([], [], 0)
            try:
                imported, skipped_in_transaction = _import_database(
                    storage, prepared, recommendation,
                    import_preferences=categories["preferences"],
                    migrate_preferences=migrate_preferences)
            except BaseException:
                for path in created:
                    path.unlink(missing_ok=True)
                raise
            return {
                "liked_imported": imported,
                "liked_skipped": skipped_existing + skipped_in_transaction,
                "preference_evidence": (sum(row["value"] is not None for row in recommendation["evidence"])
                                        if recommendation is not None else 0),
                "preference_rebuild_required": migrate_preferences,
                "categories": categories,
                "backup": backup,
                "artifact_revision": storage.artifact_revision(),
            }
    except zipfile.BadZipFile:
        raise ValidationError("The selected file is not a valid user-data ZIP archive.") from None
