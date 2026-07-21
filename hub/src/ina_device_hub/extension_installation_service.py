import hashlib
import io
import json
import os
import re
import stat
import uuid
import zipfile
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from ina_device_hub.ai_content_service import ai_content_service
from ina_device_hub.extension_manifest import MAX_MANIFEST_BYTES, ExtensionManifestValidationError, validate_extension_manifest
from ina_device_hub.extension_registry import list_extensions, reload_extension_registry
from ina_device_hub.json_repository_io import atomic_write_json, repository_file_lock
from ina_device_hub.setting import setting

MAX_PACKAGE_BYTES = 512 * 1024
MAX_PACKAGE_MEMBERS = 4
MAX_COMPRESSION_RATIO = 100
_REVIEW_ID = re.compile(r"^[0-9a-f-]{36}$")
_ACTIVE_CONTENT_MARKERS = ("<script", "javascript:", "data:text/html", "onerror=", "onload=")
_PROMPT_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "監査を無視",
    "以前の指示を無視",
    "システムプロンプト",
)


class ExtensionReviewError(ValueError):
    pass


class ExtensionInstallError(ValueError):
    pass


def _finding(severity, category, title, detail):
    return {"severity": severity, "category": category, "title": title, "detail": detail}


class ExtensionInstallationService:
    def __init__(self, work_dir=None, ai_service=None):
        self.work_dir = Path(work_dir or setting().get_work_dir()).expanduser()
        self.root = self.work_dir / "extensions"
        self.review_dir = self.root / "reviews"
        self.installed_dir = self.root / "installed"
        self.audit_log_path = self.root / "audit.jsonl"
        self.ai_service = ai_service or ai_content_service()

    def review_upload(self, filename, payload, *, reviewed_by=""):
        if not isinstance(payload, bytes) or not payload:
            raise ExtensionReviewError("追加機能ファイルが空です。")
        if len(payload) > MAX_PACKAGE_BYTES:
            raise ExtensionReviewError("追加機能ファイルが大きすぎます。上限は512KBです。")
        safe_filename = Path(str(filename or "extension.json")).name[:160]
        sha256 = hashlib.sha256(payload).hexdigest()
        findings = []
        manifest = None
        try:
            manifest, package_findings = self._read_package(safe_filename, payload)
            findings.extend(package_findings)
            validate_extension_manifest(manifest)
            findings.append(_finding("pass", "schema", "定義形式を確認", "許可された宣言型UIフィールドだけが含まれています。"))
            findings.extend(self._static_content_findings(manifest))
        except (ExtensionReviewError, ExtensionManifestValidationError, json.JSONDecodeError, UnicodeDecodeError, zipfile.BadZipFile, RecursionError) as exc:
            findings.append(_finding("block", "package", "インストールできない形式", str(exc)))

        blockers = [item for item in findings if item["severity"] == "block"]
        install_allowed = manifest is not None and not blockers
        ai_audit = self._pending_ai_audit() if install_allowed else self._not_run_ai_audit("定義の静的検査を通過していないため、AI監査を実行できません。")
        overall_risk = self._overall_risk(findings, ai_audit, install_allowed)
        review_id = str(uuid.uuid4())
        record = {
            "schema_version": 1,
            "id": review_id,
            "status": "reviewed" if install_allowed else "blocked",
            "created_at": datetime.now(UTC).isoformat(),
            "reviewed_by": str(reviewed_by or "")[:254],
            "filename": safe_filename,
            "sha256": sha256,
            "package_size": len(payload),
            "manifest": manifest,
            "static_findings": findings,
            "ai_audit": ai_audit,
            "install_allowed": install_allowed,
            "overall_risk": overall_risk,
            "installed_at": "",
        }
        self._save_review(record)
        self._append_audit_event("reviewed", record, actor=reviewed_by)
        return record

    def audit_review(self, review_id, *, consent_confirmed=False, approved_by=""):
        if consent_confirmed is not True:
            raise ExtensionReviewError("AI監査へ送信する前に、確認ダイアログで同意してください。")
        with repository_file_lock(str(self.root / ".mutations")):
            record = self.get_review(review_id)
            if not record.get("install_allowed") or not isinstance(record.get("manifest"), dict):
                raise ExtensionReviewError("静的検査で拒否された追加機能はAI監査を実行できません。")
            if (record.get("ai_audit") or {}).get("status") == "completed":
                raise ExtensionReviewError("AI監査はすでに完了しています。")
            record["ai_audit_consent"] = {
                "confirmed": True,
                "confirmed_at": datetime.now(UTC).isoformat(),
                "confirmed_by": str(approved_by or "")[:254],
                "shared_data": ["validated_manifest", "static_findings"],
            }
            self._append_audit_event("ai_audit_approved", record, actor=approved_by)
            record["ai_audit"] = self.ai_service.audit_extension_manifest(record["manifest"], record.get("static_findings") or [])
            record["ai_audit_approved_at"] = datetime.now(UTC).isoformat()
            record["ai_audit_approved_by"] = str(approved_by or "")[:254]
            record["overall_risk"] = self._overall_risk(record.get("static_findings") or [], record["ai_audit"], True)
            self._save_review(record)
            self._append_audit_event("ai_audit_completed", record, actor=approved_by)
            return record

    def install_review(self, review_id, *, installed_by=""):
        with repository_file_lock(str(self.root / ".mutations")):
            record = self.get_review(review_id)
            if record.get("status") == "installed":
                raise ExtensionInstallError("この追加機能はすでにインストールされています。")
            if not record.get("install_allowed") or not isinstance(record.get("manifest"), dict):
                raise ExtensionInstallError("静的検査で拒否された追加機能はインストールできません。")
            if (record.get("ai_audit") or {}).get("status") not in {"completed", "unavailable"}:
                raise ExtensionInstallError("インストール前にAI監査の確認と実行が必要です。")
            manifest = record["manifest"]
            validate_extension_manifest(manifest)
            extension_id = manifest["id"]
            version = manifest["version"]
            existing_ids = {item["id"] for item in list_extensions()}
            if extension_id in existing_ids:
                raise ExtensionInstallError("同じIDの追加機能がすでにあります。更新と提供元確認は今後の署名対応後に行えます。")
            target = self.installed_dir / extension_id / version
            if target.exists():
                raise ExtensionInstallError("同じバージョンがすでに保存されています。")
            target.mkdir(parents=True, mode=0o700)
            os.chmod(target.parent, 0o700)
            os.chmod(target, 0o700)
            manifest_path = target / "extension.json"
            atomic_write_json(str(manifest_path), manifest)
            os.chmod(manifest_path, 0o600)
            reload_extension_registry()
            record["status"] = "installed"
            record["installed_at"] = datetime.now(UTC).isoformat()
            record["installed_by"] = str(installed_by or "")[:254]
            self._save_review(record)
            self._append_audit_event("installed", record, actor=installed_by)
            return {"extension": {**manifest, "source": "installed"}, "review": record}

    def get_review(self, review_id):
        if not isinstance(review_id, str) or not _REVIEW_ID.fullmatch(review_id):
            raise ExtensionReviewError("監査IDが正しくありません。")
        try:
            canonical_id = str(uuid.UUID(review_id))
        except ValueError as exc:
            raise ExtensionReviewError("監査IDが正しくありません。") from exc
        path = self.review_dir / f"{canonical_id}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise ExtensionReviewError("監査結果が見つかりません。") from exc
        if not isinstance(value, dict) or value.get("id") != canonical_id:
            raise ExtensionReviewError("監査結果が破損しています。")
        return value

    def installed_extensions(self):
        return [item for item in list_extensions() if str(item.get("source") or "").startswith("installed:")]

    def bundled_extensions(self):
        return [item for item in list_extensions() if not str(item.get("source") or "").startswith("installed:")]

    def _read_package(self, filename, payload):
        suffix = Path(filename).suffix.lower()
        if suffix == ".json":
            if len(payload) > MAX_MANIFEST_BYTES:
                raise ExtensionReviewError("extension.jsonが大きすぎます。")
            manifest = json.loads(payload.decode("utf-8"))
            return manifest, [_finding("pass", "package", "単一JSONを確認", "実行ファイルを含まないextension.jsonです。")]
        if suffix not in {".inas-extension", ".zip"}:
            raise ExtensionReviewError("extension.jsonまたは.inas-extensionファイルを選択してください。")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_PACKAGE_MEMBERS:
                raise ExtensionReviewError("パッケージ内のファイル数が許容範囲を超えています。")
            files = []
            for member in members:
                normalized = member.filename.replace("\\", "/")
                if normalized.startswith("/") or ".." in normalized.split("/") or normalized != "extension.json":
                    raise ExtensionReviewError("Version 1では直下のextension.json以外を同梱できません。")
                if member.is_dir() or stat.S_ISLNK(member.external_attr >> 16) or member.flag_bits & 0x1:
                    raise ExtensionReviewError("ディレクトリ、シンボリックリンク、暗号化ファイルは同梱できません。")
                if member.file_size > MAX_MANIFEST_BYTES:
                    raise ExtensionReviewError("展開後のextension.jsonが大きすぎます。")
                if member.compress_size == 0 and member.file_size > 0:
                    raise ExtensionReviewError("圧縮率を安全に検証できません。")
                if member.compress_size and member.file_size / member.compress_size > MAX_COMPRESSION_RATIO:
                    raise ExtensionReviewError("圧縮率が高すぎるため、安全に展開できません。")
                files.append(member)
            if len(files) != 1:
                raise ExtensionReviewError("パッケージにはextension.jsonを1件だけ含めてください。")
            manifest = json.loads(archive.read(files[0]).decode("utf-8"))
        return manifest, [_finding("pass", "package", "安全なパッケージ構造", "パス、件数、展開サイズ、圧縮率を確認しました。")]

    def _static_content_findings(self, manifest):
        findings = []
        extension_id = manifest["id"]
        lowered = json.dumps(manifest, ensure_ascii=False).lower()
        if extension_id.startswith("jp.inas.official"):
            findings.append(_finding("block", "identity", "公式IDを確認できません", "UIアップロードでは公式名前空間を使用できません。"))
        if extension_id in {item["id"] for item in list_extensions()}:
            findings.append(_finding("block", "identity", "同じIDが登録済み", "既存Extensionの上書きは署名による提供元確認が実装されるまで禁止しています。"))
        if any(marker in lowered for marker in _ACTIVE_CONTENT_MARKERS):
            findings.append(_finding("block", "active_content", "実行可能な表現を検出", "説明文にもスクリプトやイベント属性を含めることはできません。"))
        if any(marker in lowered for marker in _PROMPT_INJECTION_MARKERS):
            findings.append(
                _finding(
                    "warning",
                    "prompt_injection",
                    "監査を操作するような文章",
                    "AI監査への命令として解釈されないよう隔離しました。提供者の意図を確認してください。",
                )
            )
        if "公式" in f"{manifest.get('name', '')} {manifest.get('description', '')}" and not extension_id.startswith("jp.inas.official"):
            findings.append(
                _finding("warning", "identity", "公式と誤認する可能性", "表示名または説明に『公式』が含まれますが、署名済み公式パッケージではありません。")
            )
        findings.append(_finding("pass", "execution", "実行コードなし", "Version 1の許可リストにより、Python、JavaScript、HTML、シェルは実行されません。"))
        findings.append(_finding("pass", "permissions", "機器操作権限なし", "DB、MQTT、GPIO、秘密情報、ネットワークへのアクセスは提供されません。"))
        return findings

    @staticmethod
    def _pending_ai_audit():
        return {
            "status": "pending_consent",
            "risk_level": "unknown",
            "summary": "AI監査はまだ実行していません。実行前に送信内容と料金の可能性を確認します。",
            "findings": [],
            "recommendation": "AI監査を開始するか、インストールしないでください。",
            "model": "",
        }

    @staticmethod
    def _not_run_ai_audit(summary):
        return {
            "status": "not_run",
            "risk_level": "unknown",
            "summary": summary,
            "findings": [],
            "recommendation": "静的検査結果を確認してください。",
            "model": "",
        }

    @staticmethod
    def _overall_risk(findings, ai_audit, install_allowed):
        if not install_allowed:
            return "blocked"
        if ai_audit.get("risk_level") == "high":
            return "high"
        if any(item["severity"] == "warning" for item in findings) or ai_audit.get("risk_level") in {"medium", "unknown"}:
            return "medium"
        return "low"

    def _save_review(self, record):
        self.review_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.review_dir, 0o700)
        path = self.review_dir / f"{record['id']}.json"
        atomic_write_json(str(path), record)
        os.chmod(path, 0o600)

    def _append_audit_event(self, event, record, *, actor=""):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        payload = {
            "occurred_at": datetime.now(UTC).isoformat(),
            "event": event,
            "review_id": record.get("id"),
            "extension_id": (record.get("manifest") or {}).get("id", ""),
            "version": (record.get("manifest") or {}).get("version", ""),
            "sha256": record.get("sha256", ""),
            "actor": str(actor or "")[:254],
            "overall_risk": record.get("overall_risk", ""),
            "ai_audit_consent": bool((record.get("ai_audit_consent") or {}).get("confirmed")),
            "ai_model": str((record.get("ai_audit") or {}).get("model") or "")[:160],
        }
        with repository_file_lock(str(self.audit_log_path)):
            with self.audit_log_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n")
                file.flush()
                os.fsync(file.fileno())
            os.chmod(self.audit_log_path, 0o600)


@lru_cache(maxsize=1)
def extension_installation_service():
    return ExtensionInstallationService()
