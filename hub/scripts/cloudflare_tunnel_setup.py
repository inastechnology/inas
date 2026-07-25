#!/usr/bin/env python3
"""Provision and run a Cloudflare Tunnel for ina-device-hub.

The provisioning path uses the Cloudflare API token from hub/.env and does not
require `cloudflared tunnel login`.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from cloudflare_setup_common import ScriptError, merged_env, quote_env_value, require_any_value, require_value, upsert_env_file

API_BASE_URL = "https://api.cloudflare.com/client/v4"
DEFAULT_TUNNEL_NAME = "inas-hub"
DEFAULT_ORIGIN_URL = "http://127.0.0.1:39151"
MANAGED_DNS_COMMENT = "Managed by ina-device-hub Cloudflare hosted setup"


def log(message: str) -> None:
    print(message, file=sys.stderr)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


class CloudflareAPI:
    def __init__(self, account_id: str, token: str, dry_run: bool = False) -> None:
        self.account_id = account_id
        self.token = token
        self.dry_run = dry_run

    def account_path(self, path: str) -> str:
        return f"/accounts/{self.account_id}{path}"

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        *,
        account_scoped: bool = True,
        dry_result: Any | None = None,
    ) -> Any:
        api_path = self.account_path(path) if account_scoped else path
        url = f"{API_BASE_URL}{api_path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"

        if self.dry_run and method.upper() != "GET":
            log(f"[dry-run] {method.upper()} {api_path}")
            if body is not None:
                redacted = json.dumps(redact(body), ensure_ascii=False, indent=2, sort_keys=True)
                log(redacted)
            return dry_result if dry_result is not None else {"id": f"dry-run-{path.strip('/').replace('/', '-')}", **(body or {})}

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
            raise CloudflareAPIError(method.upper(), url, exc.code, payload) from exc
        except urllib.error.URLError as exc:
            raise ScriptError(f"Cloudflare API request failed: {method.upper()} {url}\n{exc}") from exc

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ScriptError(f"Cloudflare API returned non-JSON response: {payload[:500]}") from exc

        if not parsed.get("success", False):
            raise ScriptError(f"Cloudflare API returned errors for {method.upper()} {url}:\n{json.dumps(parsed, ensure_ascii=False, indent=2)}")
        return parsed.get("result")


class CloudflareAPIError(ScriptError):
    def __init__(self, method: str, url: str, status_code: int, payload: str) -> None:
        self.method = method
        self.url = url
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"Cloudflare API failed: {method} {url}\nHTTP {status_code}: {payload}")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("<redacted>" if "token" in key.lower() or "secret" in key.lower() else redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def context(args: argparse.Namespace) -> tuple[dict[str, str], CloudflareAPI, Path]:
    env_file = Path(args.env_file).resolve()
    env = merged_env(env_file)
    account_id = require_value(env, "CLOUDFLARE_ACCOUNT_ID")
    token = require_any_value(env, ["CLOUDFLARE_ACCESS_API_TOKEN", "CLOUDFLARE_API_TOKEN"])
    return env, CloudflareAPI(account_id, token, getattr(args, "dry_run", False)), env_file


def tunnel_name(args: argparse.Namespace, env: dict[str, str]) -> str:
    return args.name or env.get("CLOUDFLARE_TUNNEL_NAME") or DEFAULT_TUNNEL_NAME


def tunnel_hostname(args: argparse.Namespace, env: dict[str, str]) -> str:
    value = args.hostname or env.get("CLOUDFLARE_TUNNEL_HOSTNAME") or env.get("CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME")
    if not value:
        raise ScriptError("Missing hostname. Set CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME or CLOUDFLARE_TUNNEL_HOSTNAME.")
    return value.strip().rstrip(".")


def tunnel_origin_url(args: argparse.Namespace, env: dict[str, str]) -> str:
    return args.origin_url or env.get("CLOUDFLARE_TUNNEL_ORIGIN_URL") or DEFAULT_ORIGIN_URL


def list_tunnels(api: CloudflareAPI, name: str) -> list[dict[str, Any]]:
    result = api.request("GET", "/cfd_tunnel", query={"name": name, "is_deleted": "false", "per_page": 100})
    if not isinstance(result, list):
        return []
    return [item for item in result if item.get("name") == name and not item.get("deleted_at")]


def assert_remote_tunnel(tunnel: dict[str, Any], name: str) -> None:
    if tunnel.get("name") != name:
        raise ScriptError(f"CLOUDFLARE_TUNNEL_ID points to tunnel named {tunnel.get('name')}, expected {name}.")
    if tunnel.get("config_src") == "local" or tunnel.get("remote_config") is False:
        raise ScriptError(f"Tunnel {name} ({tunnel.get('id')}) is locally-managed. Use a different CLOUDFLARE_TUNNEL_NAME or remove that tunnel.")


def get_or_create_tunnel(api: CloudflareAPI, name: str, tunnel_id: str | None = None) -> dict[str, Any]:
    if tunnel_id:
        tunnel = api.request("GET", f"/cfd_tunnel/{tunnel_id}")
        if not isinstance(tunnel, dict) or tunnel.get("deleted_at"):
            raise ScriptError(f"CLOUDFLARE_TUNNEL_ID does not point to an active tunnel: {tunnel_id}")
        assert_remote_tunnel(tunnel, name)
        log(f"Using existing Cloudflare Tunnel by id: {name} ({tunnel.get('id')})")
        return tunnel

    tunnels = list_tunnels(api, name)
    if len(tunnels) > 1:
        ids = ", ".join(str(tunnel.get("id")) for tunnel in tunnels)
        raise ScriptError(f"Multiple Cloudflare Tunnels named {name} exist: {ids}. Set CLOUDFLARE_TUNNEL_ID to the intended tunnel.")
    if tunnels:
        tunnel = tunnels[0]
        assert_remote_tunnel(tunnel, name)
        log(f"Using existing Cloudflare Tunnel: {name} ({tunnel.get('id')})")
        return tunnel

    log(f"Creating Cloudflare Tunnel: {name}")
    return api.request(
        "POST",
        "/cfd_tunnel",
        {"name": name, "config_src": "cloudflare"},
        dry_result={"id": "<created-tunnel-id>", "name": name, "config_src": "cloudflare"},
    )


def put_tunnel_config(api: CloudflareAPI, tunnel_id: str, hostname: str, origin_url: str) -> dict[str, Any]:
    payload = {
        "config": {
            "ingress": [
                {"hostname": hostname, "service": origin_url},
                {"service": "http_status:404"},
            ],
        },
    }
    log(f"Configuring Cloudflare Tunnel ingress: {hostname} -> {origin_url}")
    return api.request("PUT", f"/cfd_tunnel/{tunnel_id}/configurations", payload, dry_result={"tunnel_id": tunnel_id, **payload})


def get_tunnel_token(api: CloudflareAPI, tunnel_id: str) -> str:
    token = api.request("GET", f"/cfd_tunnel/{tunnel_id}/token")
    if not isinstance(token, str) or not token:
        raise ScriptError("Cloudflare API did not return a tunnel token.")
    return token


def hostname_zone_candidates(hostname: str) -> list[str]:
    parts = hostname.strip(".").split(".")
    candidates = [".".join(parts[index:]) for index in range(max(0, len(parts) - 2), len(parts) - 1)]
    if len(parts) >= 2:
        apex = ".".join(parts[-2:])
        candidates.append(apex)
    output: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in output:
            output.append(candidate)
    return output


def list_zones(api: CloudflareAPI, query: dict[str, Any]) -> list[dict[str, Any]]:
    result = api.request("GET", "/zones", query=query, account_scoped=False)
    if not isinstance(result, list):
        return []
    return result


def find_zone(api: CloudflareAPI, env: dict[str, str], hostname: str) -> dict[str, Any]:
    if env.get("CLOUDFLARE_ZONE_ID"):
        zone_id = env["CLOUDFLARE_ZONE_ID"].strip()
        result = api.request("GET", f"/zones/{zone_id}", account_scoped=False)
        if isinstance(result, dict):
            return result
        raise ScriptError(f"Could not read CLOUDFLARE_ZONE_ID={zone_id}")

    zone_name = env.get("CLOUDFLARE_ZONE_NAME", "").strip()
    candidates = [zone_name] if zone_name else hostname_zone_candidates(hostname)
    for candidate in candidates:
        zones = list_zones(api, {"name": candidate, "account.id": api.account_id, "per_page": 50})
        if zones:
            return zones[0]

    raise ScriptError(f"Could not find a Cloudflare zone for hostname: {hostname}. Set CLOUDFLARE_ZONE_ID or CLOUDFLARE_ZONE_NAME.")


def list_dns_records(api: CloudflareAPI, zone_id: str, hostname: str, record_type: str | None = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"name": hostname, "per_page": 100}
    if record_type:
        query["type"] = record_type
    result = api.request("GET", f"/zones/{zone_id}/dns_records", query=query, account_scoped=False)
    if not isinstance(result, list):
        return []
    return result


def get_dns_record(api: CloudflareAPI, zone_id: str, record_id: str) -> dict[str, Any]:
    record = api.request("GET", f"/zones/{zone_id}/dns_records/{record_id}", account_scoped=False)
    if not isinstance(record, dict):
        raise ScriptError(f"DNS record not found: {record_id}")
    return record


def dns_record_matches(record: dict[str, Any], hostname: str, target: str) -> bool:
    return record.get("type") == "CNAME" and record.get("name") == hostname and record.get("content") == target and record.get("proxied") is True


def upsert_dns_record(api: CloudflareAPI, zone_id: str, hostname: str, tunnel_id: str, dns_record_id: str | None = None) -> dict[str, Any]:
    target = f"{tunnel_id}.cfargotunnel.com"
    payload = {
        "type": "CNAME",
        "name": hostname,
        "content": target,
        "ttl": 1,
        "proxied": True,
        "comment": MANAGED_DNS_COMMENT,
    }

    if dns_record_id:
        record = get_dns_record(api, zone_id, dns_record_id)
        if record.get("type") != "CNAME" or record.get("name") != hostname:
            raise ScriptError(f"CLOUDFLARE_TUNNEL_DNS_RECORD_ID points to {record.get('type')} {record.get('name')}, expected CNAME {hostname}.")
        if dns_record_matches(record, hostname, target):
            log(f"DNS CNAME is already up to date: {hostname} -> {target}")
            return record
        log(f"Updating managed DNS CNAME by id: {hostname} -> {target}")
        return api.request("PUT", f"/zones/{zone_id}/dns_records/{record['id']}", payload, account_scoped=False, dry_result={"id": record["id"], **payload})

    all_records = list_dns_records(api, zone_id, hostname)
    blocking = [record for record in all_records if record.get("type") != "CNAME"]
    if blocking:
        types = ", ".join(str(record.get("type")) for record in blocking)
        raise ScriptError(f"DNS record {hostname} already exists with non-CNAME type(s): {types}. Remove or change it before provisioning the tunnel.")

    cname_records = [record for record in all_records if record.get("type") == "CNAME"]
    if len(cname_records) > 1:
        ids = ", ".join(str(record.get("id")) for record in cname_records)
        raise ScriptError(f"Multiple CNAME records already exist for {hostname}: {ids}. Set CLOUDFLARE_TUNNEL_DNS_RECORD_ID to the intended record.")
    if cname_records:
        record = cname_records[0]
        if dns_record_matches(record, hostname, target):
            log(f"DNS CNAME is already up to date: {hostname} -> {target}")
            return record
        if record.get("comment") != MANAGED_DNS_COMMENT:
            raise ScriptError(
                f"DNS CNAME {hostname} already exists but is not marked as managed by ina-device-hub. "
                "Set CLOUDFLARE_TUNNEL_DNS_RECORD_ID to allow updating that specific record, or choose another hostname."
            )
        log(f"Updating DNS CNAME: {hostname} -> {target}")
        return api.request("PUT", f"/zones/{zone_id}/dns_records/{record['id']}", payload, account_scoped=False, dry_result={"id": record["id"], **payload})

    log(f"Creating DNS CNAME: {hostname} -> {target}")
    return api.request("POST", f"/zones/{zone_id}/dns_records", payload, account_scoped=False, dry_result={"id": "<created-dns-record-id>", **payload})


def write_token_file(env_file: Path, token: str) -> Path:
    token_file = env_file.parent / ".data" / "cloudflare" / "tunnel-token"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token + "\n", encoding="utf-8")
    token_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
    try:
        display_path = token_file.relative_to(env_file.parent)
    except ValueError:
        display_path = token_file
    log(f"Wrote tunnel token file: {display_path}")
    return token_file


def print_env_summary(updates: dict[str, str]) -> None:
    print("")
    print("# Add or update these values in hub/.env")
    for key in sorted(updates):
        value = "<redacted>" if "TOKEN" in key else updates[key]
        if value:
            print(f"{key}={quote_env_value(value)}")


def cmd_check(args: argparse.Namespace) -> None:
    env, api, _ = context(args)
    hostname = tunnel_hostname(args, env)

    failures: list[str] = []
    try:
        tunnels = list_tunnels(api, tunnel_name(args, env))
        print(f"Cloudflare Tunnel API: ok ({len(tunnels)} tunnel(s) with configured name)")
    except ScriptError as exc:
        print("Cloudflare Tunnel API: failed")
        failures.append(f"Cloudflare Tunnel API failed: {exc}")

    try:
        zone = find_zone(api, env, hostname)
        print(f"Cloudflare Zone API: ok ({zone.get('name')})")
        records = list_dns_records(api, str(zone.get("id")), hostname)
        print(f"Cloudflare DNS Records API: read ok ({len(records)} record(s) with target hostname; write is checked during provision)")
    except ScriptError as exc:
        print("Cloudflare Zone/DNS API: failed")
        failures.append(f"Cloudflare Zone/DNS API failed: {exc}")

    if failures:
        raise ScriptError("Cloudflare Tunnel check failed:\n" + "\n\n".join(failures))
    print("Cloudflare Tunnel check passed.")


def cmd_provision(args: argparse.Namespace) -> None:
    env, api, env_file = context(args)
    name = tunnel_name(args, env)
    hostname = tunnel_hostname(args, env)
    origin_url = tunnel_origin_url(args, env)

    tunnel = get_or_create_tunnel(api, name, env.get("CLOUDFLARE_TUNNEL_ID", "").strip() or None)
    tunnel_id = str(tunnel.get("id") or "")
    if not tunnel_id:
        raise ScriptError("Cloudflare Tunnel id is missing.")

    put_tunnel_config(api, tunnel_id, hostname, origin_url)
    token = "<dry-run-token>" if args.dry_run else get_tunnel_token(api, tunnel_id)

    token_file = env.get("CLOUDFLARE_TUNNEL_TOKEN_FILE", "")
    if args.write_env and not args.dry_run:
        token_path = write_token_file(env_file, token)
        token_file = str(token_path)

    updates = {
        "HUB_HTTP_SERVER": "waitress",
        "HUB_AUTH_MODE": "cloudflare_access",
        "CLOUDFLARE_TUNNEL_NAME": name,
        "CLOUDFLARE_TUNNEL_ID": tunnel_id,
        "CLOUDFLARE_TUNNEL_HOSTNAME": hostname,
        "CLOUDFLARE_TUNNEL_ORIGIN_URL": origin_url,
        "CLOUDFLARE_TUNNEL_TOKEN_FILE": token_file,
    }
    if args.write_env and not args.dry_run:
        upsert_env_file(env_file, updates)

    try:
        zone = find_zone(api, env, hostname)
        zone_id = str(zone.get("id") or "")
        zone_name = str(zone.get("name") or "")
        partial_zone_updates = {"CLOUDFLARE_ZONE_ID": zone_id, "CLOUDFLARE_ZONE_NAME": zone_name}
        if args.write_env and not args.dry_run:
            upsert_env_file(env_file, partial_zone_updates)
    except ScriptError as exc:
        raise ScriptError(f"{exc}\nTunnel was created/configured, but DNS setup did not complete. Fix the issue above and rerun this command.") from exc

    try:
        dns_record = upsert_dns_record(api, zone_id, hostname, tunnel_id, env.get("CLOUDFLARE_TUNNEL_DNS_RECORD_ID", "").strip() or None)
    except CloudflareAPIError as exc:
        if exc.status_code == 403 and "/dns_records" in exc.url:
            raise ScriptError(
                f"{exc}\n"
                "Tunnel was created/configured, but DNS setup did not complete. "
                "Grant the API token zone-scoped DNS Write permission "
                f"(Cloudflare dashboard: Zone > DNS > Edit) for zone {zone_name} ({zone_id}), then rerun this command."
            ) from exc
        raise ScriptError(f"{exc}\nTunnel was created/configured, but DNS setup did not complete. Fix the issue above and rerun this command.") from exc
    except ScriptError as exc:
        raise ScriptError(f"{exc}\nTunnel was created/configured, but DNS setup did not complete. Fix the issue above and rerun this command.") from exc

    updates.update(
        {
            "CLOUDFLARE_TUNNEL_DNS_RECORD_ID": str(dns_record.get("id") or ""),
            "CLOUDFLARE_ZONE_ID": zone_id,
            "CLOUDFLARE_ZONE_NAME": zone_name,
        }
    )
    if args.write_env and not args.dry_run:
        upsert_env_file(env_file, updates)
        log(f"Updated {env_file}")
    print_env_summary(updates)


def resolve_cloudflared(env: dict[str, str]) -> str | None:
    configured = env.get("CLOUDFLARE_CLOUDFLARED_BIN", "").strip()
    if configured:
        return configured if Path(configured).exists() else None
    bundled = repo_root() / ".data" / "bin" / "cloudflared"
    if bundled.exists():
        return str(bundled)
    return shutil.which("cloudflared")


def cloudflared_download_url() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux" and machine in ("x86_64", "amd64"):
        return "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
    if system == "linux" and machine in ("aarch64", "arm64"):
        return "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
    raise ScriptError(f"Automatic cloudflared download is not supported for {platform.system()} {platform.machine()}. Install cloudflared manually.")


def install_cloudflared() -> Path:
    target = repo_root() / ".data" / "bin" / "cloudflared"
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    url = cloudflared_download_url()
    log(f"Downloading cloudflared to {target}")
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            target.write_bytes(response.read())
    except urllib.error.URLError as exc:
        raise ScriptError(f"Failed to download cloudflared from {url}: {exc}") from exc
    target.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    return target


def load_tunnel_token(env: dict[str, str], api: CloudflareAPI | None = None) -> str:
    token_file = env.get("CLOUDFLARE_TUNNEL_TOKEN_FILE", "").strip()
    if token_file and Path(token_file).exists():
        return Path(token_file).read_text(encoding="utf-8").strip()
    token = env.get("CLOUDFLARE_TUNNEL_TOKEN", "").strip()
    if token:
        return token
    tunnel_id = env.get("CLOUDFLARE_TUNNEL_ID", "").strip()
    if api and tunnel_id:
        return get_tunnel_token(api, tunnel_id)
    raise ScriptError("Missing tunnel token. Run `python3 scripts/cloudflare_tunnel_setup.py --write-env provision` first.")


def cmd_install_cloudflared(args: argparse.Namespace) -> None:
    path = install_cloudflared()
    print(path)


def cmd_start(args: argparse.Namespace) -> None:
    env, api, _ = context(args)
    binary = resolve_cloudflared(env)
    if not binary and args.install_cloudflared:
        binary = str(install_cloudflared())
    if not binary:
        raise ScriptError(
            "cloudflared is not installed. Run `python3 scripts/cloudflare_tunnel_setup.py install-cloudflared` or install it with your package manager."
        )

    token = load_tunnel_token(env, api)
    run_env = os.environ.copy()
    run_env["TUNNEL_TOKEN"] = token
    cmd = [binary, "tunnel", "--no-autoupdate", "--loglevel", args.loglevel, "run"]
    log(f"Starting Cloudflare Tunnel with {binary}")
    os.execvpe(binary, cmd, run_env)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision and run Cloudflare Tunnel for ina-device-hub.")
    parser.add_argument("--env-file", default=str(repo_root() / ".env"), help="Path to .env. Default: hub/.env")
    parser.add_argument("--dry-run", action="store_true", help="Print write requests without changing Cloudflare.")
    parser.add_argument("--write-env", action="store_true", help="Write generated values back to --env-file.")
    parser.add_argument("--name", help=f"Tunnel name. Default: {DEFAULT_TUNNEL_NAME}")
    parser.add_argument("--hostname", help="Public hostname. Defaults to CLOUDFLARE_TUNNEL_HOSTNAME or CLOUDFLARE_HOSTED_PUBLIC_HOSTNAME.")
    parser.add_argument("--origin-url", help=f"Local origin URL. Default: {DEFAULT_ORIGIN_URL}")

    subparsers = parser.add_subparsers(dest="command", required=True)
    check_cmd = subparsers.add_parser("check", help="Check Cloudflare Tunnel, Zone, and DNS permissions.")
    check_cmd.set_defaults(func=cmd_check)

    provision_cmd = subparsers.add_parser("provision", help="Create/reuse tunnel, remote config, token file, and DNS CNAME.")
    provision_cmd.set_defaults(func=cmd_provision)

    install_cmd = subparsers.add_parser("install-cloudflared", help="Download cloudflared into hub/.data/bin without sudo.")
    install_cmd.set_defaults(func=cmd_install_cloudflared)

    start_cmd = subparsers.add_parser("start", help="Start cloudflared using the provisioned tunnel token.")
    start_cmd.add_argument("--install-cloudflared", action="store_true", help="Download cloudflared if it is not installed.")
    start_cmd.add_argument("--loglevel", default="info", help="cloudflared log level. Default: info")
    start_cmd.set_defaults(func=cmd_start)

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
