#!/usr/bin/env python3
"""Validate the minimum production configuration for MMG."""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request


DEFAULT_SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    app_env = os.environ.get("APP_ENV", "development").lower()
    secret_key = os.environ.get("SECRET_KEY", "")
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    database_url = os.environ.get("DATABASE_URL", "")
    frontend_base_url = os.environ.get("FRONTEND_BASE_URL", "")
    cors_origins = os.environ.get("CORS_ORIGINS", "")

    if app_env != "production":
        warnings.append("APP_ENV is not production.")
    if not secret_key or secret_key == DEFAULT_SECRET_KEY or secret_key.startswith("CHANGE_ME"):
        errors.append("SECRET_KEY must be unique and non-default.")
    if len(secret_key) < 32:
        errors.append("SECRET_KEY should be at least 32 characters.")
    if not admin_password or admin_password == "1234" or admin_password.startswith("CHANGE_ME"):
        errors.append("ADMIN_PASSWORD must be set and non-default.")
    if "CHANGE_ME" in database_url:
        errors.append("DATABASE_URL contains a placeholder value.")
    if "CHANGE_ME" in os.environ.get("POSTGRES_PASSWORD", ""):
        errors.append("POSTGRES_PASSWORD contains a placeholder value.")
    if not database_url:
        errors.append("DATABASE_URL is required.")
    if not frontend_base_url:
        errors.append("FRONTEND_BASE_URL is required.")
    if not cors_origins:
        errors.append("CORS_ORIGINS is required.")
    if "localhost" in cors_origins or "127.0.0.1" in cors_origins:
        warnings.append("CORS_ORIGINS contains localhost; verify this is intentional.")

    for name, url in [("backend", os.environ.get("BACKEND_HEALTH_URL")), ("frontend", os.environ.get("FRONTEND_HEALTH_URL"))]:
        if not url:
            continue
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status >= 400:
                    errors.append(f"{name} health returned HTTP {response.status}.")
        except urllib.error.URLError as exc:
            errors.append(f"{name} health failed: {exc}.")

    for warning in warnings:
        print(f"WARN: {warning}")
    for error in errors:
        print(f"FAIL: {error}")

    if errors:
        return 1
    print("OK: production configuration baseline is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
