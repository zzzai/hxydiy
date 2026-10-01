"""Authenticated source-card fact tool. Preview by default; never access the DB."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def input_digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def prepare_request(payload, preview=None):
    body = dict(payload)
    card_id = body.pop("card_id")
    store_id = body.pop("store_id", None)
    if type(card_id) is not int or card_id <= 0 or (store_id is not None and (type(store_id) is not int or store_id <= 0)):
        raise ValueError("positive card_id and store_id are required")
    if any(key in body for key in ("apply", "expected_version", "preview_token")):
        raise ValueError("control fields are supplied by the tool, not the input")
    body["apply"] = preview is not None
    if preview is not None:
        if preview.get("input_sha256") != input_digest(payload) or preview.get("applied") is not False:
            raise ValueError("input changed or preview is not an unapplied preview")
        if not body.get("idempotency_key"):
            raise ValueError("apply requires an idempotency_key in the original input")
        body["expected_version"] = preview["version"]
        body["preview_token"] = preview["preview_token"]
    suffix = "?" + urlencode({"store_id": store_id}) if store_id is not None else ""
    return f"/api/v1/admin/v2/membership-cards/{card_id}/facts{suffix}", body


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--token-env", default="HXY_STAFF_TOKEN")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--preview-file", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.apply != bool(args.preview_file):
            raise ValueError("--apply requires --preview-file; preview does not accept it")
        if args.report.resolve() in {args.input.resolve(), args.preview_file.resolve() if args.preview_file else None}:
            raise ValueError("report must not overwrite input or preview")
        if args.report.exists() or not args.report.parent.is_dir():
            raise ValueError("report must be a new file in an existing private directory")
        token = os.environ.get(args.token_env)
        if not token:
            raise ValueError("staff token environment variable is missing")
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        preview = json.loads(args.preview_file.read_text(encoding="utf-8")) if args.preview_file else None
        path, body = prepare_request(payload, preview)
        request = Request(args.base_url.rstrip("/") + path, data=json.dumps(body).encode(),
                          headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
        if result.get("applied") is not args.apply:
            raise ValueError("server result did not confirm the requested operation")
        report = {**result, "input_sha256": input_digest(payload)}
        with os.fdopen(os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
        print(json.dumps({"applied": result["applied"], "report": str(args.report)}))
        return 0
    except HTTPError as error:
        print(json.dumps({"error": "server_rejected", "http_status": error.code}))
    except (ValueError, KeyError, OSError, TypeError):
        print(json.dumps({"error": "input_credentials_or_report_invalid"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
