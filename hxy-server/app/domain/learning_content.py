"""Validate immutable learning packages before any database action."""
import hashlib
import json
from pathlib import Path


def load_package(manifest_path: Path):
    manifest = json.loads(manifest_path.read_text())
    filename = manifest["content_file"]
    if Path(filename).name != filename:
        raise ValueError("invalid_content_path")
    content_path = manifest_path.parent / filename
    if content_path.is_symlink():
        raise ValueError("content_symlink")
    raw = content_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["content_sha256"]:
        raise ValueError("content_digest_changed")
    courses = json.loads(raw)
    if len(courses) != manifest["courses"] or sum(len(c["questions"]) for c in courses) != manifest["questions"]:
        raise ValueError("content_count_mismatch")
    if len({(c["id"], c["version"]) for c in courses}) != len(courses):
        raise ValueError("duplicate_course_version")
    approved = manifest.get("status") == "approved" and bool(manifest.get("production_approval_reference"))
    for c in courses:
        if not all(isinstance(c.get(k), str) and c[k].strip() for k in ("id", "version", "title", "category", "minutes", "intro")):
            raise ValueError("course_fields_missing")
        if approved and ("pilot" in c["version"] or "preview" in c["version"]):
            raise ValueError("nonproduction_course_version")
        evidence = c["sourceEvidence"]
        sources = manifest.get("sources", [manifest | {"reference_kind": "pdf_metadata_date"}])
        if not any(all(evidence.get(k) == source[k] for k in ("reference_kind", "document_sha256")) and
                   ("question_document_sha256" not in source or evidence.get("question_document_sha256") == source["question_document_sha256"])
                   for source in sources):
            raise ValueError("course_source_mismatch")
        if not c["sources"] or not c["sections"] or not c["questions"]:
            raise ValueError("empty_course")
        if len({s["id"] for s in c["sections"]}) != len(c["sections"]):
            raise ValueError("duplicate_section")
        if len({q["id"] for q in c["questions"]}) != len(c["questions"]):
            raise ValueError("duplicate_question")
        for q in c["questions"]:
            if (type(q["answer"]) is not int or not 0 <= q["answer"] < len(q["choices"])
                    or not q["explanation"].strip() or len(q["choices"]) < 2
                    or not all(isinstance(choice, str) and choice.strip() for choice in q["choices"])):
                raise ValueError("invalid_question")
    return manifest, courses, approved
