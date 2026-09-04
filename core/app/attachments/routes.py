# SPDX-License-Identifier: Apache-2.0
"""Pièces jointes sur une entité (chantier 4.12,
docs/superpowers/specs/2026-09-04-sp40-pieces-jointes-design.md).

Routes créées en Tâche 3. Ce module existe en stub pour que lint-imports
valide l'exemption app.attachments.routes -> app.ingestion.storage définie
en Tâche 1."""

from app.ingestion import storage as _  # noqa: F401

__all__ = []
