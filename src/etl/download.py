"""Скачивание и регистрация сырых данных в data/raw/ + запись в MANIFEST.md.

Команды:
    uv run python -m src.etl.download wdi [--force]
        Снимок WDI через API Всемирного банка.
    uv run python -m src.etl.download register FILE --dataset NAME --version V --url URL
        Файл, скачанный вручную (AidData, BACI), — посчитать хеш и записать в манифест.
    uv run python -m src.etl.download verify
        Сверить все файлы с хешами из манифеста.

Принципы: raw только пишем один раз и потом читаем; повторный запуск ничего не ломает
(идемпотентность); любое несовпадение хеша — громкая ошибка, а не молчаливая перезапись.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.etl.countries import AFRICA_ISO3, YEARS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "MANIFEST.md"

# Показатели WDI: исходы + контрольные переменные
WDI_INDICATORS = {
    "NY.GDP.MKTP.KD": "ВВП, пост. USD 2015",
    "NY.GDP.PCAP.KD": "ВВП на душу, пост. USD 2015",
    "NY.GDP.MKTP.KD.ZG": "Рост ВВП, %",
    "NE.EXP.GNFS.KD": "Экспорт товаров и услуг, пост. USD 2015",
    "NE.EXP.GNFS.ZS": "Экспорт, % ВВП",
    "NY.GDP.TOTL.RT.ZS": "Ресурсная рента, % ВВП (конфаундер: сырьевой бум)",
    "NE.GDI.TOTL.ZS": "Валовое накопление капитала, % ВВП",
    "SP.POP.TOTL": "Население",
}
WDI_API = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"


# ---------- хеши и манифест ----------

def sha256(path: Path, chunk: int = 1 << 20) -> str:
    """SHA-256 по кускам 1 МБ: файл BACI на несколько ГБ не грузим в память целиком."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def read_manifest() -> dict[str, dict[str, str]]:
    """Строки таблицы MANIFEST.md -> {имя файла: запись}."""
    cols = ["dataset", "version", "file", "url", "downloaded", "sha256"]
    rows: dict[str, dict[str, str]] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != len(cols) or cells[0] in ("Датасет", "---"):
            continue
        rec = dict(zip(cols, cells))
        rows[rec["file"]] = rec
    return rows


def add_to_manifest(path: Path, dataset: str, version: str, url: str) -> None:
    digest = sha256(path)
    known = read_manifest().get(path.name)
    if known:
        if known["sha256"] == digest:
            print(f"= {path.name}: уже в манифесте, хеш совпадает")
            return
        sys.exit(
            f"! {path.name}: хеш НЕ совпадает с манифестом.\n"
            f"  манифест: {known['sha256']}\n  файл:     {digest}\n"
            "  Новая версия данных? Сохрани её под новым именем, raw не перезаписываем."
        )
    row = f"| {dataset} | {version} | {path.name} | {url} | {date.today()} | {digest} |\n"
    with MANIFEST.open("a", encoding="utf-8") as f:
        f.write(row)
    print(f"+ {path.name}: записан в манифест (sha256 {digest[:12]}…)")


# ---------- WDI ----------

def _session() -> requests.Session:
    """HTTP-сессия с повторами: 3 попытки, паузы растут 2 → 4 → 8 с (exponential backoff).
    Повторяем таймауты и 5xx — временные сбои сервера; 4xx (наша ошибка) не повторяем."""
    retry = Retry(total=3, read=3, connect=3, backoff_factor=2,
                  status_forcelist=(429, 500, 502, 503, 504))
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def fetch_wdi_indicator(indicator: str) -> list[dict]:
    """Один показатель для 54 стран за 2000–2021. API отдаёт [метаданные, записи]."""
    url = WDI_API.format(countries=";".join(sorted(AFRICA_ISO3)), indicator=indicator)
    params = {"format": "json", "date": f"{YEARS[0]}:{YEARS[-1]}", "per_page": 20000}
    resp = _session().get(url, params=params, timeout=60)
    resp.raise_for_status()
    meta, records = resp.json()
    if meta["pages"] != 1:  # защита: всё должно прийти одной страницей
        raise RuntimeError(f"{indicator}: {meta['pages']} страниц, ожидалась 1")
    return records


def download_wdi(force: bool = False) -> None:
    out = RAW / f"wdi_snapshot_{date.today():%Y%m%d}.json"
    if out.exists() and not force:
        print(f"= {out.name} уже есть (--force, чтобы перекачать)")
    else:
        snapshot = {}
        for code, label in WDI_INDICATORS.items():
            records = fetch_wdi_indicator(code)
            filled = sum(r["value"] is not None for r in records)
            print(f"  {code:<20} {len(records):>5} записей, {filled:>5} непустых — {label}")
            snapshot[code] = records
        # sort_keys + фиксированный отступ: одинаковые данные -> побайтово одинаковый файл
        out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1, sort_keys=True),
                       encoding="utf-8")
    add_to_manifest(out, "WDI", f"API v2, снимок {out.stem.split('_')[-1]}",
                    "https://api.worldbank.org/v2")


# ---------- проверка ----------

def verify() -> None:
    rows = read_manifest()
    if not rows:
        print("Манифест пуст")
        return
    bad = 0
    for name, rec in rows.items():
        path = RAW / name
        if not path.exists():
            print(f"? {name}: файла нет (скачай по URL из манифеста)")
            bad += 1
        elif sha256(path) != rec["sha256"]:
            print(f"! {name}: хеш не совпадает")
            bad += 1
        else:
            print(f"ok {name}")
    if bad:
        sys.exit(f"{bad} проблем(ы)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("wdi")
    w.add_argument("--force", action="store_true")

    r = sub.add_parser("register")
    r.add_argument("file", type=Path)
    r.add_argument("--dataset", required=True)
    r.add_argument("--version", required=True)
    r.add_argument("--url", required=True)

    sub.add_parser("verify")
    args = p.parse_args()

    if args.cmd == "wdi":
        download_wdi(args.force)
    elif args.cmd == "register":
        path = args.file.resolve()
        if path.parent != RAW:
            sys.exit(f"Сначала положи файл в {RAW}")
        add_to_manifest(path, args.dataset, args.version, args.url)
    else:
        verify()


if __name__ == "__main__":
    main()
