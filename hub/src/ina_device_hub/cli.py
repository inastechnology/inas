import argparse
from pathlib import Path

from ina_device_hub.configuration_cli import DEFAULT_ENV_PATH, EnvDocument, check_configuration, configure, install
from ina_device_hub.state_backup import create_state_backup, restore_state_backup


def _parser():
    parser = argparse.ArgumentParser(prog="ina-hub", description="INA Device Hub setup utility")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (("install", "対話式に.envを作成する"), ("configure", "対話式に.envの設定を変更する")):
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH), help="対象.envファイル")
        subparser.add_argument("--skip-checks", action="store_true", help="接続確認を省略する")
    check_parser = subparsers.add_parser("check", help="設定・外部接続を非対話で確認する")
    check_parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH), help="対象.envファイル")
    check_parser.add_argument("--production", action="store_true", help="Cloudflare公開用の本番条件も確認する")
    check_parser.add_argument("--skip-connections", action="store_true", help="外部接続確認を省略する")
    backup_parser = subparsers.add_parser("backup", help="Hub状態を世代バックアップする")
    backup_parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH), help="対象.envファイル")
    restore_parser = subparsers.add_parser("restore", help="Hub状態をバックアップから復元する")
    restore_parser.add_argument("archive", help="復元するtar.gz")
    restore_parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH), help="対象.envファイル")
    restore_parser.add_argument("--force", action="store_true", help="サービス停止済みであることを確認して復元する")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.command == "install":
        return install(args.env_file, args.skip_checks)
    if args.command == "configure":
        return configure(args.env_file, args.skip_checks)
    if args.command == "check":
        return check_configuration(args.env_file, production=args.production, skip_connections=args.skip_connections)

    values = EnvDocument.load(Path(args.env_file)).values
    work_dir = values.get("WORK_DIR") or "~/.ina-device-hub"
    backup_dir = values.get("HUB_BACKUP_DIR") or str(Path(work_dir).expanduser() / "backups")
    if args.command == "backup":
        archive = create_state_backup(work_dir, backup_dir, retention=int(values.get("HUB_BACKUP_RETENTION") or 14))
        print(f"Hub state backup created: {archive}")
        return 0
    if not args.force:
        print("復元前にHubサービスを停止し、--forceを指定してください。")
        return 2
    restored = restore_state_backup(args.archive, work_dir)
    print(f"Hub state restored: {len(restored)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
