#!/usr/bin/env python3
"""Provision Cloudflare Access for the hosted hub option.

This script intentionally does not create or store Cloudflare API tokens.
Set CLOUDFLARE_ACCESS_API_TOKEN in your shell or in hub/.env before running it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_BASE_URL = "https://api.cloudflare.com/client/v4"
DEFAULT_APP_NAME = "inas-hub-hosted"
DEFAULT_GROUP_NAME = "inas-hub-allowed-users"
DEFAULT_POLICY_NAME = "inas-hub-allow-email-group"
DEFAULT_SESSION_DURATION = "4h"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ScriptError(RuntimeError):
    pass


def log(message: str) -> None:
    print(message, file=sys.stderr)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def merged_env(env_file: Path) -> dict[str, str]:
    values = parse_env_file(env_file)
    values.update({key: value for key, value in os.environ.items() if value is not None})
    return values


def quote_env_value(value: str) -> str:
    if not value:
        return ""
    if re.search(r"\s|#|['\"]", value):
        return json.dumps(value, ensure_ascii=False)
    return value


def upsert_env_file(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key = stripped.split("=", 1)[0]
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        else:
            key = key.strip()

        if key in updates:
            output.append(f"{key}={quote_env_value(updates[key])}")
            seen.add(key)
        else:
            output.append(line)

    if output and output[-1] != "":
        output.append("")
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={quote_env_value(value)}")

    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not EMAIL_RE.match(normalized):
        raise ScriptError(f"Invalid email address: {email}")
    return normalized


def parse_email_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[,\s]+", raw)
    return [normalize_email(part) for part in parts if part.strip()]


def read_email_file(path: Path) -> list[str]:
    emails: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        emails.append(normalize_email(line))
    return emails


def collect_emails(args: argparse.Namespace, env: dict[str, str]) -> list[str]:
    emails: list[str] = []
    emails.extend(parse_email_list(env.get("CLOUDFLARE_ACCESS_ALLOWED_EMAILS")))
    for email in getattr(args, "email", []) or []:
        emails.append(normalize_email(email))
    email_file = getattr(args, "email_file", None)
    if email_file:
        emails.extend(read_email_file(Path(email_file)))
    return sorted(set(emails))


class CloudflareAPI:
    def __init__(self, account_id: str, token: str, dry_run: bool = False) -> None:
        self.account_id = account_id
        self.token = token
        self.dry_run = dry_run

    def account_path(self, path: str) -> str:
        return f"/accounts/{self.account_id}{path}"

    def request(self, method: str, path: str, body: dict[str, Any] | None = None, query: dict[str, Any] | None = None) -> Any:
        url = f"{API_BASE_URL}{self.account_path(path)}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"

        if self.dry_run and method.upper() != "GET":
            log(f"[dry-run] {method.upper()} {self.account_path(path)}")
            log(json.dumps(body or {}, ensure_ascii=False, indent=2, sort_keys=True))
            return {"id": f"dry-run-{path.strip('/').replace('/', '-')}", **(body or {})}

        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            raise ScriptError(f"Cloudflare API failed: {method.upper()} {url}\nHTTP {exc.code}: {payload}") from exc
        except urllib.error.URLError as exc:
            raise ScriptError(f"Cloudflare API request failed: {method.upper()} {url}\n{exc}") from exc

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ScriptError(f"Cloudflare API returned non-JSON response: {payload[:500]}") from exc

        if not parsed.get("success", False):
            raise ScriptError(f"Cloudflare API returned errors for {method.upper()} {url}:\n{json.dumps(parsed, ensure_ascii=False, indent=2)}")
        return parsed.get("result")

    def list_all(self, path: str, query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params = {"per_page": 100, "page": 1}
        if query:
            params.update(query)
        results: list[dict[str, Any]] = []

        while True:
            page = self.request("GET", path, query=params)
            if not isinstance(page, list):
                return results
            results.extend(page)
            if len(page) < int(params["per_page"]):
                return results
            params["page"] = int(params["page"]) + 1


def email_rule(email: str) -> dict[str, dict[str, str]]:
    return {"email": {"email": email}}


def rule_email(rule: dict[str, Any]) -> str | None:
    email = rule.get("email")
    if isinstance(email, dict) and isinstance(email.get("email"), str):
        return email["email"].strip().lower()
    return None


def group_emails(group: dict[str, Any]) -> list[str]:
    emails = []
    for rule in group.get("include", []) or []:
        email = rule_email(rule)
        if email:
            emails.append(email)
    return sorted(set(emails))


def group_payload(name: str, emails: list[str], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    if not emails:
        raise ScriptError("Access group must contain at least one allowed email.")

    existing_include = (existing or {}).get("include", []) or []
    preserved_include = [rule for rule in existing_include if not rule_email(rule)]
    payload: dict[str, Any] = {
        "name": name,
        "include": preserved_include + [email_rule(email) for email in emails],
    }
    for key in ("exclude", "require"):
        if existing and existing.get(key):
            payload[key] = existing[key]
    return payload


def find_group(api: CloudflareAPI, group_id: str | None, group_name: str) -> dict[str, Any] | None:
    if group_id:
        try:
            return api.request("GET", f"/access/groups/{group_id}")
        except ScriptError:
            log(f"Warning: CLOUDFLARE_ACCESS_GROUP_ID was not found, falling back to name lookup: {group_name}")

    groups = api.list_all("/access/groups", {"name": group_name})
    exact_groups = [group for group in groups if group.get("name") == group_name]
    if len(exact_groups) > 1:
        ids = ", ".join(str(group.get("id")) for group in exact_groups)
        raise ScriptError(f"Multiple Access groups named {group_name} exist: {ids}. Set CLOUDFLARE_ACCESS_GROUP_ID to the intended group.")
    if exact_groups:
        return exact_groups[0]
    return None


def comparable_rules(rules: list[dict[str, Any]] | None) -> list[str]:
    return sorted(json.dumps(rule, sort_keys=True, separators=(",", ":")) for rule in (rules or []))


def group_matches(group: dict[str, Any], payload: dict[str, Any]) -> bool:
    return (
        group.get("name") == payload.get("name")
        and comparable_rules(group.get("include")) == comparable_rules(payload.get("include"))
        and comparable_rules(group.get("exclude")) == comparable_rules(payload.get("exclude"))
        and comparable_rules(group.get("require")) == comparable_rules(payload.get("require"))
    )


def create_or_update_group(api: CloudflareAPI, group_name: str, emails: list[str], group_id: str | None = None) -> dict[str, Any]:
    existing = find_group(api, group_id, group_name)
    payload = group_payload(group_name, emails, existing)
    if existing and existing.get("id"):
        if group_matches(existing, payload):
            log(f"Access group is already up to date: {group_name} ({existing['id']})")
            return existing
        log(f"Updating Access group: {group_name} ({existing['id']})")
        return api.request("PUT", f"/access/groups/{existing['id']}", payload)

    log(f"Creating Access group: {group_name}")
    return api.request("POST", "/access/groups", payload)


def backup_group(env_file: Path, group: dict[str, Any]) -> None:
    backup_dir = repo_root() / ".data" / "cloudflare-access-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    group_id = group.get("id", "unknown")
    path = backup_dir / f"{timestamp}-{group_id}.json"
    path.write_text(json.dumps(group, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        display_path = path.relative_to(env_file.parent)
    except ValueError:
        display_path = path
    log(f"Backed up current Access group to {display_path}")


def find_application(api: CloudflareAPI, app_id: str | None, hostname: str, app_name: str) -> dict[str, Any] | None:
    if app_id:
        try:
            return api.request("GET", f"/access/apps/{app_id}")
        except ScriptError:
            log(f"Warning: CLOUDFLARE_ACCESS_APP_ID was not found, falling back to hostname lookup: {hostname}")

    apps = api.list_all("/access/apps", {"domain": hostname, "exact": "true"})
    exact_domain_apps = [app for app in apps if app.get("domain") == hostname and app.get("type") == "self_hosted"]
    if len(exact_domain_apps) > 1:
        ids = ", ".join(str(app.get("id")) for app in exact_domain_apps)
        raise ScriptError(f"Multiple Access applications for {hostname} exist: {ids}. Set CLOUDFLARE_ACCESS_APP_ID to the intended app.")
    if exact_domain_apps:
        return exact_domain_apps[0]

    apps = api.list_all("/access/apps", {"name": app_name, "exact": "true"})
    exact_name_apps = [app for app in apps if app.get("name") == app_name and app.get("type") == "self_hosted"]
    if len(exact_name_apps) > 1:
        ids = ", ".join(str(app.get("id")) for app in exact_name_apps)
        raise ScriptError(f"Multiple Access applications named {app_name} exist: {ids}. Set CLOUDFLARE_ACCESS_APP_ID to the intended app.")
    if exact_name_apps:
        return exact_name_apps[0]
    return None


def app_destinations_include_hostname(app: dict[str, Any], hostname: str) -> bool:
    destinations = app.get("destinations") or []
    if not isinstance(destinations, list):
        return False
    return any(isinstance(destination, dict) and destination.get("type") == "public" and destination.get("uri") == hostname for destination in destinations)


def create_or_get_application(api: CloudflareAPI, app_name: str, hostname: str, session_duration: str, app_id: str | None = None) -> dict[str, Any]:
    existing = find_application(api, app_id, hostname, app_name)
    if existing and existing.get("id"):
        log(f"Using existing Access application: {existing.get('name')} ({existing['id']})")
        if (
            existing.get("domain") == hostname
            and app_destinations_include_hostname(existing, hostname)
            and existing.get("session_duration") == session_duration
        ):
            return existing

        payload = dict(existing)
        for key in ("id", "created_at", "updated_at", "aud"):
            payload.pop(key, None)
        payload.update(
            {
                "name": app_name,
                "type": "self_hosted",
                "domain": hostname,
                "destinations": [{"type": "public", "uri": hostname}],
                "session_duration": session_duration,
                "app_launcher_visible": True,
            }
        )
        log(f"Updating Access application: {app_name} ({existing['id']})")
        return api.request("PUT", f"/access/apps/{existing['id']}", payload)

    payload = {
        "name": app_name,
        "type": "self_hosted",
        "domain": hostname,
        "destinations": [{"type": "public", "uri": hostname}],
        "session_duration": session_duration,
        "app_launcher_visible": True,
    }
    log(f"Creating Access application: {app_name} ({hostname})")
    return api.request("POST", "/access/apps", payload)


def find_policy(api: CloudflareAPI, app_id: str, policy_id: str | None, policy_name: str) -> dict[str, Any] | None:
    if policy_id:
        try:
            return api.request("GET", f"/access/apps/{app_id}/policies/{policy_id}")
        except ScriptError:
            log(f"Warning: CLOUDFLARE_ACCESS_POLICY_ID was not found, falling back to name lookup: {policy_name}")

    policies = api.list_all(f"/access/apps/{app_id}/policies")
    exact_policies = [policy for policy in policies if policy.get("name") == policy_name]
    if len(exact_policies) > 1:
        ids = ", ".join(str(policy.get("id")) for policy in exact_policies)
        raise ScriptError(f"Multiple Access policies named {policy_name} exist on app {app_id}: {ids}. Set CLOUDFLARE_ACCESS_POLICY_ID.")
    if exact_policies:
        return exact_policies[0]
    return None


def policy_matches(policy: dict[str, Any], payload: dict[str, Any]) -> bool:
    return (
        policy.get("name") == payload.get("name")
        and policy.get("decision") == payload.get("decision")
        and int(policy.get("precedence") or 0) == int(payload.get("precedence") or 0)
        and policy.get("session_duration") == payload.get("session_duration")
        and comparable_rules(policy.get("include")) == comparable_rules(payload.get("include"))
        and comparable_rules(policy.get("exclude")) == comparable_rules(payload.get("exclude"))
        and comparable_rules(policy.get("require")) == comparable_rules(payload.get("require"))
    )


def create_or_update_policy(
    api: CloudflareAPI,
    app_id: str,
    group_id: str,
    policy_name: str,
    session_duration: str,
    policy_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "name": policy_name,
        "decision": "allow",
        "include": [{"group": {"id": group_id}}],
        "precedence": 1,
        "session_duration": session_duration,
    }
    existing = find_policy(api, app_id, policy_id, policy_name)
    if existing and existing.get("id"):
        if policy_matches(existing, payload):
            log(f"Access policy is already up to date: {policy_name} ({existing['id']})")
            return existing
        log(f"Updating Access policy: {policy_name} ({existing['id']})")
        return api.request("PUT", f"/access/apps/{app_id}/policies/{existing['id']}", payload)

    log(f"Creating Access policy: {policy_name}")
    return api.request("POST", f"/access/apps/{app_id}/policies", payload)


def normalize_team_domain(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://{value}"


def resolve_team_domain(api: CloudflareAPI, env: dict[str, str]) -> str:
    configured = normalize_team_domain(env.get("CLOUDFLARE_ACCESS_TEAM_DOMAIN", ""))
    try:
        organization = api.request("GET", "/access/organizations")
    except ScriptError as exc:
        log(f"Warning: could not read Zero Trust organization: {exc}")
        return configured

    if isinstance(organization, dict):
        auth_domain = organization.get("auth_domain")
        if isinstance(auth_domain, str) and auth_domain.strip():
            actual = normalize_team_domain(auth_domain)
            if configured and configured != actual:
                log(f"Warning: using Access auth_domain from Cloudflare API instead of CLOUDFLARE_ACCESS_TEAM_DOMAIN: {actual}")
            return actual
    return configured


def require_value(env: dict[str, str], key: str) -> str:
    value = env.get(key, "").strip()
    if not value:
        raise ScriptError(f"Missing required env value: {key}")
    return value


def require_any_value(env: dict[str, str], keys: list[str]) -> str:
    for key in keys:
        value = env.get(key, "").strip()
        if value:
            return value
    raise ScriptError(f"Missing required env value: one of {', '.join(keys)}")


def print_env_summary(values: dict[str, str]) -> None:
    print("")
    print("# Add or update these values in hub/.env")
    for key in sorted(values):
        if values[key]:
            print(f"{key}={quote_env_value(values[key])}")


def access_context(args: argparse.Namespace) -> tuple[dict[str, str], CloudflareAPI, Path]:
    env_file = Path(args.env_file).resolve()
    env = merged_env(env_file)
    account_id = require_value(env, "CLOUDFLARE_ACCOUNT_ID")
    token = require_any_value(env, ["CLOUDFLARE_ACCESS_API_TOKEN", "CLOUDFLARE_API_TOKEN"])
    return env, CloudflareAPI(account_id, token, getattr(args, "dry_run", False)), env_file


def cmd_provision(args: argparse.Namespace) -> None:
    env, api, env_file = access_context(args)
    hostname = args.hostname or env.get("CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME") or env.get("CLOUDFLARE_TUNNEL_HOSTNAME")
    if not hostname:
        raise ScriptError("Missing hosted hostname. Set CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME or pass --hostname.")

    group_name = args.group_name or env.get("CLOUDFLARE_ACCESS_GROUP_NAME") or DEFAULT_GROUP_NAME
    app_name = args.app_name or env.get("CLOUDFLARE_ACCESS_APP_NAME") or DEFAULT_APP_NAME
    policy_name = args.policy_name or env.get("CLOUDFLARE_ACCESS_POLICY_NAME") or DEFAULT_POLICY_NAME
    session_duration = args.session_duration or env.get("CLOUDFLARE_ACCESS_SESSION_DURATION") or DEFAULT_SESSION_DURATION
    emails = collect_emails(args, env)

    if not emails and not env.get("CLOUDFLARE_ACCESS_GROUP_ID"):
        raise ScriptError("Set at least one allowed email via --email, --email-file, or CLOUDFLARE_ACCESS_ALLOWED_EMAILS.")

    group = find_group(api, env.get("CLOUDFLARE_ACCESS_GROUP_ID"), group_name)
    if emails:
        if group and not args.dry_run and not group_matches(group, group_payload(group_name, emails, group)):
            backup_group(env_file, group)
        group = create_or_update_group(api, group_name, emails, env.get("CLOUDFLARE_ACCESS_GROUP_ID"))
    if not group or not group.get("id"):
        raise ScriptError("Could not create or find Access group.")

    app = create_or_get_application(api, app_name, hostname, session_duration, env.get("CLOUDFLARE_ACCESS_APP_ID"))
    if not app or not app.get("id"):
        raise ScriptError("Could not create or find Access application.")

    policy = create_or_update_policy(
        api,
        app["id"],
        group["id"],
        policy_name,
        session_duration,
        env.get("CLOUDFLARE_ACCESS_POLICY_ID"),
    )

    team_domain = resolve_team_domain(api, env)
    updates = {
        "CLOUDFLARE_ACCOUNT_ID": env["CLOUDFLARE_ACCOUNT_ID"],
        "CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME": hostname,
        "CLOUDFLARE_ACCESS_TEAM_DOMAIN": team_domain,
        "CLOUDFLARE_ACCESS_POLICY_AUD": str(app.get("aud") or ""),
        "CLOUDFLARE_ACCESS_GROUP_ID": str(group["id"]),
        "CLOUDFLARE_ACCESS_APP_ID": str(app["id"]),
        "CLOUDFLARE_ACCESS_POLICY_ID": str((policy or {}).get("id") or ""),
    }
    if args.write_env and not args.dry_run:
        upsert_env_file(env_file, updates)
        log(f"Updated {env_file}")
    print_env_summary(updates)


def cmd_check(args: argparse.Namespace) -> None:
    env, api, _ = access_context(args)
    configured_team_domain = normalize_team_domain(env.get("CLOUDFLARE_ACCESS_TEAM_DOMAIN", ""))

    actual_team_domain = ""
    failures: list[str] = []

    try:
        organization = api.request("GET", "/access/organizations")
        if isinstance(organization, dict):
            actual_team_domain = normalize_team_domain(str(organization.get("auth_domain") or ""))
        print("Zero Trust organization: ok")
    except ScriptError as exc:
        print("Zero Trust organization: failed")
        failures.append(f"Zero Trust organization read failed: {exc}")

    try:
        groups = api.request("GET", "/access/groups", query={"per_page": 1, "page": 1})
        group_count = len(groups) if isinstance(groups, list) else 0
        print(f"Access groups: ok ({group_count} readable on first page)")
    except ScriptError as exc:
        print("Access groups: failed")
        failures.append(f"Access groups read failed: {exc}")

    try:
        apps = api.request("GET", "/access/apps", query={"per_page": 1, "page": 1})
        app_count = len(apps) if isinstance(apps, list) else 0
        print(f"Access apps: ok ({app_count} readable on first page)")
    except ScriptError as exc:
        print("Access apps: failed")
        failures.append(f"Access apps read failed: {exc}")

    print(f"Access team domain: {actual_team_domain or configured_team_domain or '(not returned)'}")

    if configured_team_domain and actual_team_domain and configured_team_domain != actual_team_domain:
        print(f"Warning: CLOUDFLARE_ACCESS_TEAM_DOMAIN differs from API auth_domain: {configured_team_domain} != {actual_team_domain}", file=sys.stderr)

    if failures:
        summary = "\n\n".join(failures)
        raise ScriptError(f"Cloudflare Access API check failed:\n{summary}")

    print("Cloudflare Access API check passed.")


def load_group_for_allowlist(args: argparse.Namespace) -> tuple[dict[str, str], CloudflareAPI, Path, dict[str, Any]]:
    env, api, env_file = access_context(args)
    group_name = args.group_name or env.get("CLOUDFLARE_ACCESS_GROUP_NAME") or DEFAULT_GROUP_NAME
    group = find_group(api, env.get("CLOUDFLARE_ACCESS_GROUP_ID"), group_name)
    if not group:
        raise ScriptError("Access group not found. Run the provision command first.")
    return env, api, env_file, group


def update_group_emails(args: argparse.Namespace, target_emails: list[str]) -> dict[str, Any]:
    env, api, env_file, group = load_group_for_allowlist(args)
    if not args.dry_run:
        backup_group(env_file, group)
    payload = group_payload(group.get("name") or DEFAULT_GROUP_NAME, sorted(set(target_emails)), group)
    updated = api.request("PUT", f"/access/groups/{group['id']}", payload)
    if args.write_env and not args.dry_run:
        upsert_env_file(env_file, {"CLOUDFLARE_ACCESS_GROUP_ID": str(updated["id"])})
    return updated


def cmd_list(args: argparse.Namespace) -> None:
    _, _, _, group = load_group_for_allowlist(args)
    for email in group_emails(group):
        print(email)


def cmd_add(args: argparse.Namespace) -> None:
    _, _, _, group = load_group_for_allowlist(args)
    target = set(group_emails(group))
    for email in args.email:
        target.add(normalize_email(email))
    updated = update_group_emails(args, sorted(target))
    log(f"Updated Access group {updated.get('id')} with {len(group_emails(updated))} email(s).")


def cmd_remove(args: argparse.Namespace) -> None:
    _, _, _, group = load_group_for_allowlist(args)
    target = set(group_emails(group))
    for email in args.email:
        target.discard(normalize_email(email))
    if not target:
        raise ScriptError("Refusing to leave the Access group with zero allowed emails.")
    updated = update_group_emails(args, sorted(target))
    log(f"Updated Access group {updated.get('id')} with {len(group_emails(updated))} email(s).")


def confirm(prompt: str) -> None:
    answer = input(f"{prompt} [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        raise ScriptError("Aborted.")


def cmd_apply(args: argparse.Namespace) -> None:
    _, _, _, group = load_group_for_allowlist(args)
    current = set(group_emails(group))
    desired = set(read_email_file(Path(args.email_file)))
    if not desired:
        raise ScriptError("Refusing to apply an empty allowlist.")

    added = sorted(desired - current)
    removed = sorted(current - desired)
    if not added and not removed:
        log("Allowlist is already up to date.")
        return

    print("Emails to add:")
    for email in added:
        print(f"  + {email}")
    print("Emails to remove:")
    for email in removed:
        print(f"  - {email}")

    if not args.yes and not args.dry_run:
        confirm("Apply this allowlist?")
    updated = update_group_emails(args, sorted(desired))
    log(f"Updated Access group {updated.get('id')} with {len(group_emails(updated))} email(s).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision and manage Cloudflare Access for ina-device-hub.")
    parser.add_argument("--env-file", default=str(repo_root() / ".env"), help="Path to .env. Default: hub/.env")
    parser.add_argument("--dry-run", action="store_true", help="Print write requests without sending them.")
    parser.add_argument("--write-env", action="store_true", help="Write generated non-secret IDs back to --env-file.")
    parser.add_argument("--group-name", help=f"Access group name. Default: {DEFAULT_GROUP_NAME}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    check_cmd = subparsers.add_parser("check", help="Check Cloudflare Access API credentials and read permissions.")
    check_cmd.set_defaults(func=cmd_check)

    provision = subparsers.add_parser("provision", help="Create or reuse Access group, self-hosted app, and allow policy.")
    provision.add_argument("--hostname", help="Public hostname protected by Access. Defaults to CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME.")
    provision.add_argument("--app-name", help=f"Access application name. Default: {DEFAULT_APP_NAME}")
    provision.add_argument("--policy-name", help=f"Access policy name. Default: {DEFAULT_POLICY_NAME}")
    provision.add_argument("--session-duration", help=f"Access session duration. Default: {DEFAULT_SESSION_DURATION}")
    provision.add_argument("--email", action="append", default=[], help="Allowed email. Repeatable.")
    provision.add_argument("--email-file", help="File containing one allowed email per line.")
    provision.set_defaults(func=cmd_provision)

    list_cmd = subparsers.add_parser("list", help="List allowed emails in the Access group.")
    list_cmd.set_defaults(func=cmd_list)

    add_cmd = subparsers.add_parser("add", help="Add allowed email(s) to the Access group.")
    add_cmd.add_argument("email", nargs="+")
    add_cmd.set_defaults(func=cmd_add)

    remove_cmd = subparsers.add_parser("remove", help="Remove allowed email(s) from the Access group.")
    remove_cmd.add_argument("email", nargs="+")
    remove_cmd.set_defaults(func=cmd_remove)

    apply_cmd = subparsers.add_parser("apply", help="Replace allowed emails from a file.")
    apply_cmd.add_argument("email_file")
    apply_cmd.add_argument("--yes", action="store_true", help="Do not ask for confirmation.")
    apply_cmd.set_defaults(func=cmd_apply)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
        return 0
    except ScriptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
