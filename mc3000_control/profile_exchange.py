from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime
from typing import Any

from .battery_manager import AutomaticProgramValues, validate_automatic_program
from .profiles import ProfileValues, validate_profile
from .storage import ProfileStore

FORMAT_NAME = "mc3000-control-profiles"
FORMAT_VERSION = 1
MAX_IMPORT_BYTES = 1_000_000
MAX_PROFILES = 250
MAX_AUTOMATIC_PROFILES = 100
MAX_CATEGORIES = 50


class ProfileExchangeError(ValueError):
    pass


def export_profiles(store: ProfileStore, *, application_version: str) -> dict[str, Any]:
    categories = store.list_categories()
    return {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "application_version": application_version,
        "created_at": datetime.now(UTC).isoformat(),
        "categories": [
            {
                "key": item["key"],
                "name": item["name"],
                "description": item["description"],
                "is_builtin": item["is_builtin"],
            }
            for item in categories
        ],
        "profiles": [_portable_profile(item) for item in store.list()],
        "automatic_profiles": [
            _portable_automatic_profile(item) for item in store.list_automatic()
        ],
    }


def import_profiles(store: ProfileStore, payload: Any) -> dict[str, int]:
    if not isinstance(payload, dict):
        raise ProfileExchangeError("Die Importdatei muss ein JSON-Objekt enthalten")
    if payload.get("format") != FORMAT_NAME:
        raise ProfileExchangeError("Unbekanntes Profilformat")
    if payload.get("format_version") != FORMAT_VERSION:
        raise ProfileExchangeError("Diese Version des Profilformats wird nicht unterstützt")

    categories = _list(payload, "categories", MAX_CATEGORIES)
    profiles = _list(payload, "profiles", MAX_PROFILES)
    automatic_profiles = _list(
        payload,
        "automatic_profiles",
        MAX_AUTOMATIC_PROFILES,
    )
    prepared_profiles: list[tuple[ProfileValues, str]] = []
    for item in profiles:
        if not isinstance(item, dict):
            raise ProfileExchangeError("Ein Profil ist ungültig")
        values = _dataclass_from_mapping(ProfileValues, item)
        validate_profile(values)
        prepared_profiles.append((values, str(item.get("category_key", "general"))))

    prepared_automatic: list[tuple[AutomaticProgramValues, str]] = []
    for item in automatic_profiles:
        if not isinstance(item, dict):
            raise ProfileExchangeError("Ein Automatikprofil ist ungültig")
        values = validate_automatic_program(
            _dataclass_from_mapping(AutomaticProgramValues, item)
        )
        prepared_automatic.append(
            (values, str(item.get("category_key", "automatic")))
        )

    category_map = _import_categories(store, categories)
    for values, source_category in prepared_profiles:
        category_key = category_map.get(source_category, "general")
        store.save(values, category_key=category_key)
    for values, source_category in prepared_automatic:
        category_key = category_map.get(
            source_category,
            "automatic",
        )
        store.save_automatic(values, category_key=category_key)

    return {
        "profiles": len(prepared_profiles),
        "automatic_profiles": len(prepared_automatic),
        "categories": sum(
            1 for source, target in category_map.items() if source != target
        ),
    }


def _portable_profile(stored: Any) -> dict[str, Any]:
    return {
        **{
            field.name: getattr(stored.values, field.name)
            for field in fields(ProfileValues)
        },
        "category_key": stored.category_key,
    }


def _portable_automatic_profile(stored: Any) -> dict[str, Any]:
    return {
        **{
            field.name: getattr(stored.values, field.name)
            for field in fields(AutomaticProgramValues)
        },
        "category_key": stored.category_key,
    }


def _list(payload: dict[str, Any], key: str, maximum: int) -> list[Any]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ProfileExchangeError(f"{key} muss eine Liste sein")
    if len(value) > maximum:
        raise ProfileExchangeError(f"{key} enthält zu viele Einträge")
    return value


def _dataclass_from_mapping(data_class: Any, item: dict[str, Any]) -> Any:
    required = {field.name for field in fields(data_class)}
    missing = sorted(required - item.keys())
    if missing:
        raise ProfileExchangeError(
            "Im Profil fehlen Felder: " + ", ".join(missing)
        )
    try:
        return data_class(**{name: item[name] for name in required})
    except (TypeError, ValueError) as exc:
        raise ProfileExchangeError("Ein Profil enthält ungültige Werte") from exc


def _import_categories(
    store: ProfileStore,
    categories: list[Any],
) -> dict[str, str]:
    existing = store.list_categories()
    by_key = {str(item["key"]): str(item["key"]) for item in existing}
    by_name = {str(item["name"]).casefold(): str(item["key"]) for item in existing}
    mapping = dict(by_key)
    for item in categories:
        if not isinstance(item, dict):
            raise ProfileExchangeError("Eine Profilkategorie ist ungültig")
        source_key = str(item.get("key", "")).strip()
        name = str(item.get("name", "")).strip()
        if not source_key or not name:
            raise ProfileExchangeError("Eine Profilkategorie ist unvollständig")
        if source_key in by_key:
            mapping[source_key] = source_key
            continue
        target = by_name.get(name.casefold())
        if target is None:
            target = str(store.create_category(name)["key"])
            by_name[name.casefold()] = target
        mapping[source_key] = target
    return mapping
