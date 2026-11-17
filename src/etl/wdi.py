"""Загрузка снимка WDI из data/raw/ в аккуратную таблицу.

    from src.etl.wdi import load_wdi, to_wide
    long = load_wdi()      # iso3 | year | indicator | value
    wide = to_wide(long)   # iso3 | year | gdp | gdp_pc | ...

Raw-файл только читаем. Перед чтением сверяем хеш с MANIFEST.md:
анализ всегда идёт по зарегистрированной версии данных.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.etl.countries import AFRICA_ISO3, YEARS
from src.etl.download import RAW, WDI_INDICATORS, read_manifest, sha256

# Код WDI -> короткое имя колонки (удобно в формулах моделей: log(gdp_pc) ~ ...)
SHORT_NAMES: dict[str, str] = {
    "NY.GDP.MKTP.KD": "gdp",
    "NY.GDP.PCAP.KD": "gdp_pc",
    "NY.GDP.MKTP.KD.ZG": "growth",
    "NE.EXP.GNFS.KD": "exports",
    "NE.EXP.GNFS.ZS": "exports_pct",
    "NY.GDP.TOTL.RT.ZS": "rents",
    "NE.GDI.TOTL.ZS": "gdi",
    "SP.POP.TOTL": "pop",
}
# Словарь должен покрывать ровно те показатели, что мы скачиваем
assert SHORT_NAMES.keys() == WDI_INDICATORS.keys()


def latest_snapshot() -> Path:
    """Самый свежий wdi_snapshot_*.json из манифеста. Дата в имени YYYYMMDD,
    поэтому сортировка строк совпадает с хронологической."""
    names = sorted(n for n in read_manifest() if n.startswith("wdi_snapshot_"))
    if not names:
        raise FileNotFoundError("В манифесте нет снимков WDI: uv run python -m src.etl.download wdi")
    return RAW / names[-1]


def _check_hash(path: Path) -> None:
    rec = read_manifest().get(path.name)
    if rec is None:
        raise ValueError(f"{path.name} не зарегистрирован в MANIFEST.md")
    if sha256(path) != rec["sha256"]:
        raise ValueError(f"{path.name}: хеш не совпадает с манифестом (файл изменён?)")


def load_wdi(path: Path | None = None) -> pd.DataFrame:
    """Снимок WDI -> long DataFrame: iso3 | year | indicator | value.

    Пропуск = строка есть, value = NaN. Строка не может отсутствовать:
    на каждый показатель ровно 54 страны × 22 года.
    """
    path = Path(path) if path else latest_snapshot()
    _check_hash(path)

    raw = pd.read_json(path, typ="series")  # {код: [записи]}
    rows = [
        {"iso3": r["countryiso3code"], "year": r["date"],
         "indicator": SHORT_NAMES[code], "value": r["value"]}
        for code, records in raw.items()
        for r in records
    ]
    df = pd.DataFrame(rows).astype({"year": int, "value": float})  # None -> NaN

    _validate(df)
    return df.sort_values(["indicator", "iso3", "year"], ignore_index=True)


def _validate(df: pd.DataFrame) -> None:
    """Инварианты панели. Нарушение = громкая ошибка, а не тихий кривой график."""
    key = ["iso3", "year", "indicator"]
    dup = df.duplicated(key)
    if dup.any():
        raise ValueError(f"Дубликаты ключа {key}:\n{df.loc[dup, key].head()}")

    extra = set(df["iso3"]) - AFRICA_ISO3.keys()
    if extra:
        raise ValueError(f"Лишние страны: {sorted(extra)}")
    bad_years = set(df["year"]) - set(YEARS)
    if bad_years:
        raise ValueError(f"Годы вне периода: {sorted(bad_years)}")

    expected = len(AFRICA_ISO3) * len(YEARS)
    sizes = df.groupby("indicator").size()
    short = sizes[sizes != expected]
    if not short.empty:
        raise ValueError(f"Не {expected} строк на показатель:\n{short}")
    missing = set(SHORT_NAMES.values()) - set(sizes.index)
    if missing:
        raise ValueError(f"Нет показателей: {sorted(missing)}")


def to_wide(long: pd.DataFrame) -> pd.DataFrame:
    """long -> wide: одна строка = страна-год, показатели в колонках."""
    wide = long.pivot(index=["iso3", "year"], columns="indicator", values="value")
    wide.columns.name = None
    return wide[list(SHORT_NAMES.values())].reset_index()


if __name__ == "__main__":
    long = load_wdi()
    wide = to_wide(long)
    print(f"long: {long.shape}, wide: {wide.shape}")
    print("Доля пропусков по показателям:")
    print(wide.drop(columns=["iso3", "year"]).isna().mean().round(3).sort_values())
