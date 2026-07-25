import argparse
import json
import logging
from pathlib import Path

from ina_edge_gateway import __version__
from ina_edge_gateway.config import load_gateway_config
from ina_edge_gateway.identity import bootstrap_development_identity, load_edge_identity
from ina_edge_gateway.service import GatewayService, install_signal_handlers

DEFAULT_CONFIG_PATH = "/etc/inas/edge-gateway.json"


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "bootstrap-development-identity":
        node_id = bootstrap_development_identity(args.path)
        print(json.dumps({"node_id": node_id, "path": str(Path(args.path))}))
        return 0

    config = load_gateway_config(args.config)
    node_id = load_edge_identity(config.identity_file)
    if args.command == "check-config":
        print(
            json.dumps(
                {
                    "status": "ok",
                    "node_id": node_id,
                    "parent_configured": config.parent is not None,
                    "data_directory": str(config.data_directory),
                },
                separators=(",", ":"),
            )
        )
        return 0

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    service = GatewayService(config)
    install_signal_handlers(service)
    service.run()
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="INAS Edge Gateway")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run the Edge Gateway service")
    run_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    run_parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")

    check_parser = subparsers.add_parser("check-config", help="validate configuration and provisioned identity")
    check_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)

    identity_parser = subparsers.add_parser(
        "bootstrap-development-identity",
        help="create a development-only INAEG identity when manufacturing provisioning is unavailable",
    )
    identity_parser.add_argument("--path", required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
