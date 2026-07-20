"""Build compatible paint catalogs from manufacturer-approved public pages.

Currently supported: PPG Paints.  The PPG robots file advertises its public
sitemap, and its browse/detail pages expose color names, codes, and screen RGB
values without authentication.  Sites that reject automated requests are not
supported by this scraper.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from io import BytesIO
import json
from html import unescape
from pathlib import Path
import re
import time
from urllib.parse import urljoin
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from PIL import Image, ImageStat


BASE_URL = "https://www.ppgpaints.com"
BROWSE_URL = f"{BASE_URL}/browse-all-colors"
SOURCE_URL = "https://www.ppgpaints.com/ppg-color-families/see-all-colors"
USER_AGENT = "BlueprintMosaicStudio/1.0 (paint catalog builder)"
BENJAMIN_MOORE_SITEMAP = "https://www.benjaminmoore.com/sitemaps/colors.xml"
SWATCH_PATTERN = re.compile(
    r'href="(?P<path>/ppg-colors/[^"]+)"[^>]*>.*?'
    r'<div class="text-size-regular text-style-bold">(?P<name>.*?)</div>.*?'
    r'<div class="text-size-small text-style-bold text-color-gray">'
    r'(?P<code>PPG[^<]+)</div>',
    re.IGNORECASE | re.DOTALL,
)
RGB_PATTERN = re.compile(
    r'background-color:\s*rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CatalogLink:
    url: str
    code: str
    name: str


def fetch_text(url: str, attempts: int = 3) -> str:
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", errors="replace")
        except OSError:
            if attempt + 1 == attempts:
                raise
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def fetch_prefix(url: str, byte_count: int = 65536, attempts: int = 3) -> str:
    """Read only the document head, where Benjamin Moore publishes color meta."""
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=30) as response:
                return response.read(byte_count).decode("utf-8", errors="replace")
        except OSError:
            if attempt + 1 == attempts:
                raise
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def collect_ppg_links() -> list[CatalogLink]:
    links: dict[str, CatalogLink] = {}
    page = 1
    while True:
        url = BROWSE_URL if page == 1 else f"{BROWSE_URL}?b9b4b1c0_page={page}"
        html = fetch_text(url)
        found = 0
        for match in SWATCH_PATTERN.finditer(html):
            code = match.group("code").strip().upper()
            if code in links:
                continue
            name = re.sub(r"\s+", " ", match.group("name")).strip()
            links[code] = CatalogLink(
                url=urljoin(BASE_URL, match.group("path")),
                code=code,
                name=name,
            )
            found += 1
        print(f"Catalog page {page}: {found} new colors ({len(links)} total)")
        if found == 0:
            break
        page += 1
        time.sleep(0.1)
    return list(links.values())


def fetch_ppg_color(link: CatalogLink) -> dict[str, object]:
    html = fetch_text(link.url)
    match = RGB_PATTERN.search(html)
    if match is None:
        raise ValueError(f"No RGB value found for {link.code}: {link.url}")
    rgb = tuple(int(channel) for channel in match.groups())
    return {
        "code": link.code,
        "name": link.name,
        "rgb": list(rgb),
        "hex": "#{:02X}{:02X}{:02X}".format(*rgb),
    }


def build_ppg_catalog(workers: int) -> dict[str, object]:
    links = collect_ppg_links()
    colors = []
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        jobs = {executor.submit(fetch_ppg_color, link): link for link in links}
        for completed, future in enumerate(as_completed(jobs), 1):
            link = jobs[future]
            try:
                colors.append(future.result())
            except (OSError, ValueError) as error:
                failures.append(str(error))
            if completed % 100 == 0 or completed == len(jobs):
                print(f"Color details: {completed}/{len(jobs)}")
    if failures:
        preview = "\n".join(failures[:10])
        raise RuntimeError(
            f"Failed to collect {len(failures)} colors; catalog not written.\n{preview}"
        )
    colors.sort(key=lambda color: str(color["code"]))
    return {
        "source": SOURCE_URL,
        "catalog": "PPG Paints",
        "colors": colors,
    }


def build_behr_catalog(archive: Path) -> dict[str, object]:
    """Convert Behr's nested color-chip image archive into catalog records."""
    colors: dict[str, dict[str, object]] = {}
    with ZipFile(archive) as outer:
        for nested_name in outer.namelist():
            if not nested_name.lower().endswith(".zip"):
                continue
            with ZipFile(BytesIO(outer.read(nested_name))) as nested:
                for image_name in nested.namelist():
                    if image_name.startswith("__MACOSX/") or not image_name.lower().endswith(
                        (".jpg", ".jpeg", ".png")
                    ):
                        continue
                    stem = Path(image_name).stem
                    if stem.endswith("_250x250"):
                        stem = stem[:-8]
                    first, separator, remainder = stem.partition("_")
                    if not separator:
                        raise ValueError(f"Unrecognized Behr chip filename: {image_name}")
                    if first.isdigit():
                        name, separator, code = remainder.rpartition(" ")
                        if not separator:
                            raise ValueError(
                                f"Unrecognized Behr white-chip filename: {image_name}"
                            )
                    else:
                        code, name = first, remainder
                    code = code.strip().rstrip("*").upper()
                    name = re.sub(r"\s+", " ", name).strip().title()
                    image = Image.open(BytesIO(nested.read(image_name))).convert("RGB")
                    inset = image.crop((25, 25, image.width - 25, image.height - 25))
                    rgb = tuple(int(channel) for channel in ImageStat.Stat(inset).median)
                    if code in colors:
                        raise ValueError(f"Duplicate Behr color code: {code}")
                    colors[code] = {
                        "code": code,
                        "name": name,
                        "rgb": list(rgb),
                        "hex": "#{:02X}{:02X}{:02X}".format(*rgb),
                    }
    return {
        "source": "https://www.behr.com/consumer/colors/paint-colors",
        "catalog": "Behr Paints (2020 Color Chips)",
        "archive": archive.name,
        "colors": [colors[code] for code in sorted(colors)],
    }


def fetch_benjamin_moore_color(url: str) -> dict[str, object]:
    head = fetch_prefix(url)
    fields = {}
    for key in ("number", "name", "hex"):
        match = re.search(
            rf'name="bmc_color_{key}"\s+content="([^"]+)"',
            head,
            re.IGNORECASE,
        )
        if match is None:
            raise ValueError(f"Missing Benjamin Moore {key} metadata: {url}")
        fields[key] = unescape(match.group(1)).strip()
    hex_value = fields["hex"].lstrip("#").upper()
    if not re.fullmatch(r"[0-9A-F]{6}", hex_value):
        raise ValueError(f"Invalid Benjamin Moore hex value at {url}")
    rgb = [int(hex_value[index:index + 2], 16) for index in (0, 2, 4)]
    return {
        "code": fields["number"].upper(),
        "name": fields["name"],
        "rgb": rgb,
        "hex": f"#{hex_value}",
    }


def build_benjamin_moore_catalog(workers: int) -> dict[str, object]:
    sitemap = fetch_text(BENJAMIN_MOORE_SITEMAP)
    urls = sorted(set(re.findall(
        r"<loc>(https://www\.benjaminmoore\.com/en-us/paint-colors/color/[^<]+)</loc>",
        sitemap,
        re.IGNORECASE,
    )))
    print(f"Benjamin Moore sitemap: {len(urls):,} color pages")
    checkpoint_path = Path("data/.benjamin_moore_checkpoint.json")
    checkpoint: dict[str, dict[str, object] | None] = {}
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        print(f"Resuming {len(checkpoint):,} validated pages from checkpoint")
    colors = [record for record in checkpoint.values() if record is not None]
    failures = []
    stale_urls = [url for url, record in checkpoint.items() if record is None]
    pending_urls = [url for url in urls if url not in checkpoint]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        jobs = {
            executor.submit(fetch_benjamin_moore_color, url): url
            for url in pending_urls
        }
        for completed, future in enumerate(as_completed(jobs), 1):
            url = jobs[future]
            try:
                record = future.result()
                colors.append(record)
                checkpoint[url] = record
            except HTTPError as error:
                if error.code == 404:
                    stale_urls.append(url)
                    checkpoint[url] = None
                else:
                    failures.append(f"{url}: {error}")
            except (OSError, ValueError) as error:
                failures.append(f"{url}: {error}")
            if completed % 50 == 0 or completed == len(jobs):
                checkpoint_path.write_text(
                    json.dumps(checkpoint), encoding="utf-8"
                )
            if completed % 100 == 0 or completed == len(jobs):
                print(
                    f"Color details: {len(checkpoint)}/{len(urls)} validated",
                    flush=True,
                )
    if failures:
        preview = "\n".join(failures[:10])
        raise RuntimeError(
            f"Failed to collect {len(failures)} colors; catalog not written.\n{preview}"
        )
    by_code = {}
    duplicate_records = 0
    for color in colors:
        code = str(color["code"])
        existing = by_code.get(code)
        if existing is None:
            by_code[code] = color
            continue
        if existing != color:
            raise RuntimeError(
                f"Benjamin Moore code {code} has conflicting catalog records."
            )
        duplicate_records += 1
    checkpoint_path.unlink(missing_ok=True)
    return {
        "source": BENJAMIN_MOORE_SITEMAP,
        "catalog": "Benjamin Moore",
        "stale_sitemap_urls": stale_urls,
        "duplicate_sitemap_records": duplicate_records,
        "colors": [by_code[code] for code in sorted(by_code)],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("brand", choices=("ppg", "behr-zip", "benjamin-moore"))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if not 1 <= args.workers <= 12:
        parser.error("--workers must be between 1 and 12")
    if args.brand == "ppg":
        output = args.output or Path("data/ppg_paints.json")
        catalog = build_ppg_catalog(args.workers)
    elif args.brand == "behr-zip":
        if args.archive is None:
            parser.error("behr-zip requires --archive")
        output = args.output or Path("data/behr_paints_2020.json")
        catalog = build_behr_catalog(args.archive)
    else:
        output = args.output or Path("data/benjamin_moore.json")
        catalog = build_benjamin_moore_catalog(args.workers)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print(f"Wrote {len(catalog['colors']):,} colors to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
