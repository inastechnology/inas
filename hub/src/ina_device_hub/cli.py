import argparse

from ina_device_hub.configuration_cli import DEFAULT_ENV_PATH, configure, install


def _parser():
    parser = argparse.ArgumentParser(prog="ina-hub", description="INA Device Hub setup utility")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (("install", "対話式に.envを作成する"), ("configure", "対話式に.envの設定を変更する")):
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH), help="対象.envファイル")
        subparser.add_argument("--skip-checks", action="store_true", help="接続確認を省略する")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.command == "install":
        return install(args.env_file, args.skip_checks)
    return configure(args.env_file, args.skip_checks)


if __name__ == "__main__":
    raise SystemExit(main())
