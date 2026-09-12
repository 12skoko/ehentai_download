from __future__ import annotations

import argparse
import os

from .config import DEFAULT_CONFIG, load_management_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--management-config", default=str(DEFAULT_CONFIG))
    parser.add_argument("role", choices=("web", "supervisor"))
    args = parser.parse_args()
    config = load_management_config(args.management_config)
    os.chdir(config.repository)
    os.execv(
        str(config.python),
        [
            str(config.python),
            "-m",
            "eh_archive.cli",
            "--config-dir",
            str(config.config_dir),
            args.role,
        ],
    )


if __name__ == "__main__":
    main()
