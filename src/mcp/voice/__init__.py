#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语音模块
"""
from .wake_word_detector import (
    WakeWordDetector,
    SimpleWakeWordDetector,
    WakeWordConfig,
    create_wake_detector,
    HAS_OWW,
    HAS_PYAUDIO,
    HAS_NUMPY,
)

__all__ = [
    "WakeWordDetector",
    "SimpleWakeWordDetector",
    "WakeWordConfig",
    "create_wake_detector",
    "HAS_OWW",
    "HAS_PYAUDIO",
    "HAS_NUMPY",
]
