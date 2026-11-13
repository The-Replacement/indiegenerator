"""Stable import surface for the tintinnabuli duo planner.

The implementation lives in :mod:`indiegen.compose.techniques.t15_tintinnabuli`;
this module keeps the short name importable for callers and tests.
"""

from __future__ import annotations

from indiegen.compose.techniques.t15_tintinnabuli import plan_tintinnabuli as plan_tintinnabuli

plan_tintinnabuli_duo = plan_tintinnabuli
plan_tintinnabuli_second_voice = plan_tintinnabuli
plan_duo = plan_tintinnabuli

__all__ = (
    "plan_duo",
    "plan_tintinnabuli",
    "plan_tintinnabuli_duo",
    "plan_tintinnabuli_second_voice",
)
