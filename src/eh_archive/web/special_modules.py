from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..special.registry import VIDEO_ARCHIVE, VIDEO_ARCHIVE_KIND
from ..special.service import list_video_workflows, special_module_health

DashboardLoader = Callable[[Session], dict[str, Any]]


@dataclass(frozen=True)
class SpecialModulePage:
    kind: str
    label: str
    description: str
    template_name: str
    load_dashboard: DashboardLoader

    @property
    def url(self) -> str:
        return f"/special/modules/{self.kind}"


VIDEO_ARCHIVE_PAGE = SpecialModulePage(
    kind=VIDEO_ARCHIVE_KIND,
    label=VIDEO_ARCHIVE.label,
    description="选择图片与视频 Torrent，等待下载完成后转换并整合为普通归档产物。",
    template_name="special/video_archive.html",
    load_dashboard=list_video_workflows,
)


SPECIAL_MODULE_PAGES: dict[str, SpecialModulePage] = {
    VIDEO_ARCHIVE_PAGE.kind: VIDEO_ARCHIVE_PAGE,
}


def get_special_module_page(kind: str) -> SpecialModulePage:
    try:
        return SPECIAL_MODULE_PAGES[kind]
    except KeyError as exc:
        raise ValueError(f"unsupported special module page: {kind}") from exc


def special_module_cards(config_dir: str | Path) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "kind": page.kind,
            "label": page.label,
            "description": page.description,
            "url": page.url,
            "health": special_module_health(page.kind, config_dir),
        }
        for page in SPECIAL_MODULE_PAGES.values()
    )


def special_module_url(kind: str) -> str:
    page = SPECIAL_MODULE_PAGES.get(kind)
    return page.url if page is not None else "/special"
