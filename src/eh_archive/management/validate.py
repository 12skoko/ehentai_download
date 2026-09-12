import sys
from pathlib import Path

from ..config import load_config, load_video_archive_config


def main():
    directory = Path(sys.argv[1])
    load_config(directory)
    if (directory / "special" / "video_archive.toml").exists():
        load_video_archive_config(directory)
    from ..web.app import create_app

    create_app(config_dir=directory)


if __name__ == "__main__":
    main()
