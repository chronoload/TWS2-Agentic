#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语音唤醒词检测模块 — Hey Siri 机制

支持两种方案：
1. openWakeWord — 高性能本地唤醒词检测（仅英文）
2. SpeechRecognition — 实时语音识别匹配关键词（支持中英文）

注意：openWakeWord 目前只支持英文预训练模型。自定义中文唤醒词需要使用 SpeechRecognition 方案。
"""

import os
import re
import time
import queue
import logging
import threading
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 可选依赖
try:
    import openwakeword
    from openwakeword.model import Model as OWWModel
    HAS_OWW = True
except ImportError:
    HAS_OWW = False
    OWWModel = None

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False
    pyaudio = None

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None


@dataclass
class WakeWordConfig:
    """唤醒词检测配置"""
    # 唤醒词列表
    wake_words: List[str] = field(default_factory=lambda: ["hey_ws2", "你好ws2"])
    # 检测阈值（0-1，越高误触发越少但可能漏检）
    threshold: float = 0.5
    # 麦克风采样率
    sample_rate: int = 16000
    # 每次读取的帧数
    chunk_size: int = 1280
    # 麦克风设备索引（None=默认）
    mic_device_index: Optional[int] = None
    # 唤醒回调
    on_wake: Optional[Callable[[str], None]] = None
    # 调试模式
    debug: bool = False


class WakeWordDetector:
    """唤醒词检测器 — 使用 openWakeWord

    高性能本地唤醒词检测，但仅支持英文预训练模型。
    如果需要使用自定义中文唤醒词，请使用 SimpleWakeWordDetector。
    """

    def __init__(self, config: Optional[WakeWordConfig] = None):
        self.config = config or WakeWordConfig()
        self._model: Optional[OWWModel] = None
        self._audio_interface = None
        self._stream = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._error_queue: queue.Queue = queue.Queue()

        if not HAS_OWW:
            logger.warning("openwakeword 未安装，唤醒词检测不可用")
        if not HAS_PYAUDIO:
            logger.warning("pyaudio 未安装，麦克风不可用")
        if not HAS_NUMPY:
            logger.warning("numpy 未安装，音频处理不可用")

    def initialize(self) -> bool:
        """初始化检测模型和麦克风"""
        if not HAS_OWW:
            logger.error("openwakeword 未安装，请先运行: pip install openwakeword")
            return False
        if not HAS_PYAUDIO:
            logger.error("pyaudio 未安装，请先运行: pip install pyaudio")
            return False
        if not HAS_NUMPY:
            logger.error("numpy 未安装")
            return False

        try:
            # 下载并加载预训练模型
            # openWakeWord 内置模型：alexa, hey_mycroft, hey_jarvis, hey_rhasspy, weather, timers
            from openwakeword.utils import download_models

            # 下载默认模型
            download_models()

            # 加载所有预训练模型
            # 注意：自定义唤醒词（如 "hey_ws2"）需要自己训练模型
            # 这里使用通用模型作为基础，后续可通过关键词匹配扩展
            self._model = OWWModel(
                inference_framework="onnx",
            )

            logger.info(f"openWakeWord 模型已加载")
            logger.info(f"支持的唤醒词: {list(self._model.models.keys())}")

            # 初始化 PyAudio
            self._audio_interface = pyaudio.PyAudio()

            # 查找麦克风设备
            device_index = self._find_mic_device()
            if device_index is None:
                logger.error("未找到可用的麦克风设备")
                return False

            # 打开音频流
            self._stream = self._audio_interface.open(
                rate=self.config.sample_rate,
                format=pyaudio.paInt16,
                channels=1,
                input=True,
                frames_per_buffer=self.config.chunk_size,
                input_device_index=device_index,
            )

            logger.info(f"麦克风已打开，采样率={self.config.sample_rate}")
            return True

        except Exception as e:
            logger.error(f"初始化失败: {e}")
            return False

    def _find_mic_device(self) -> Optional[int]:
        """查找默认麦克风设备"""
        if self.config.mic_device_index is not None:
            return self.config.mic_device_index

        try:
            info = self._audio_interface.get_host_api_info_by_index(0)
            default_input = info.get("defaultInputDevice")
            if default_input is not None and default_input >= 0:
                return default_input
        except Exception:
            pass

        # 遍历所有输入设备
        for i in range(self._audio_interface.get_device_count()):
            try:
                dev_info = self._audio_interface.get_device_info_by_index(i)
                if dev_info.get("maxInputChannels", 0) > 0:
                    return i
            except Exception:
                continue

        return None

    def start(self) -> bool:
        """启动后台检测线程"""
        if self._running:
            logger.warning("检测器已在运行")
            return True

        if not self.initialize():
            return False

        self._running = True
        self._thread = threading.Thread(
            target=self._detection_loop,
            daemon=True,
            name="WakeWordDetector",
        )
        self._thread.start()
        logger.info("唤醒词检测已启动")
        return True

    def stop(self):
        """停止检测"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._audio_interface:
            self._audio_interface.terminate()
            self._audio_interface = None
        self._model = None
        logger.info("唤醒词检测已停止")

    def _detection_loop(self):
        """主检测循环"""
        logger.info("进入检测循环")

        while self._running:
            try:
                # 读取音频帧
                audio_data = self._stream.read(
                    self.config.chunk_size,
                    exception_on_overflow=False,
                )

                # 转换为 numpy 数组
                audio_np = np.frombuffer(audio_data, dtype=np.int16)
                audio_float = audio_np.astype(np.float32) / 32768.0

                # 喂给模型
                prediction = self._model.predict(audio_float)

                # 检查所有唤醒词得分
                for model_name, score in prediction.items():
                    if score >= self.config.threshold:
                        logger.info(f"检测到唤醒词: {model_name} (得分: {score:.3f})")
                        if self.config.on_wake:
                            self.config.on_wake(model_name)

            except Exception as e:
                if self._running:
                    logger.error(f"检测循环错误: {e}")
                    self._error_queue.put(e)
                time.sleep(0.1)

        logger.info("检测循环退出")

    @property
    def is_running(self) -> bool:
        return self._running

    def get_error(self, block: bool = False, timeout: float = 1.0) -> Optional[Exception]:
        """获取检测过程中的错误"""
        try:
            return self._error_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None


# ── 简单唤醒词检测器（使用 SpeechRecognition 作为备选方案）───

class SimpleWakeWordDetector:
    """简易唤醒词检测器 — 使用 speech_recognition 库

    实时语音识别，匹配关键词。支持中英文唤醒词。
    不需要自定义模型，但依赖在线语音识别服务。
    """

    def __init__(self, config: Optional[WakeWordConfig] = None):
        self.config = config or WakeWordConfig()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._recognizer = None
        self._sr = None
        self._error_queue: queue.Queue = queue.Queue()

        try:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
            self._sr = sr
        except ImportError:
            logger.warning("speech_recognition 未安装")

    def start(self) -> bool:
        if not self._recognizer:
            logger.error("speech_recognition 不可用")
            return False
        if self._running:
            return True

        # 启动前检查 PyAudio 是否可用
        try:
            import speech_recognition as sr
            sr.Microphone()  # 测试能否创建麦克风实例
        except AttributeError:
            logger.error("PyAudio 未安装，唤醒词检测不可用（请运行: pip install pyaudio）")
            return False
        except OSError:
            logger.error("未找到音频输入设备，唤醒词检测不可用")
            return False

        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="SimpleWakeWordDetector",
        )
        self._thread.start()
        logger.info(f"简易唤醒词检测已启动，监听: {self.config.wake_words}")
        return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("简易唤醒词检测已停止")

    def _listen_loop(self):
        import speech_recognition as sr

        # 检查 PyAudio 是否可用
        try:
            mic = sr.Microphone(sample_rate=self.config.sample_rate)
        except AttributeError as e:
            logger.error(f"麦克风初始化失败: {e}（请安装 PyAudio: pip install pyaudio）")
            return
        except OSError as e:
            logger.error(f"未找到音频输入设备: {e}")
            return

        # 初始化麦克风并校准环境噪声
        try:
            with mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=1.0)
                logger.info("环境噪声校准完成")
        except Exception as e:
            logger.error(f"环境噪声校准失败: {e}")
            return

        while self._running:
            try:
                with mic as source:
                    audio = self._recognizer.listen(source, timeout=2, phrase_time_limit=5)

                # 使用 whisper 或 google 识别
                try:
                    text = self._recognizer.recognize_whisper(audio, language="zh")
                except Exception:
                    try:
                        text = self._recognize_google(audio, language="zh-CN")
                    except Exception:
                        continue

                if not text:
                    continue

                # 清理文本
                text_clean = re.sub(r'[^\w\s\u4e00-\u9fff]', '', text.lower()).strip()

                # 匹配唤醒词
                for wake_word in self.config.wake_words:
                    keyword = wake_word.lower().replace(" ", "")
                    if keyword in text_clean.replace(" ", ""):
                        logger.info(f"检测到唤醒词: {wake_word} (文本: {text})")
                        if self.config.on_wake:
                            self.config.on_wake(wake_word)
                        break

            except sr.WaitTimeoutError:
                # 超时是正常的，继续监听
                continue
            except Exception as e:
                if self._running:
                    if "listening" not in str(e).lower() and "timeout" not in str(e).lower():
                        logger.debug(f"监听错误: {e}")
                time.sleep(0.1)

    def _recognize_google(self, audio, language="zh-CN"):
        """Google 语音识别（备选）"""
        try:
            return self._recognizer.recognize_google(audio, language=language)
        except Exception:
            return ""


def create_wake_detector(
    wake_words: Optional[List[str]] = None,
    on_wake: Optional[Callable[[str], None]] = None,
    threshold: float = 0.5,
) -> Any:
    """工厂函数：创建最适合的唤醒词检测器

    策略：
    - 如果唤醒词全是英文，且 openwakeword 可用，优先使用 openWakeWord
    - 否则使用 SpeechRecognition 简易检测器（支持中英文）
    """
    words = wake_words or ["hey_ws2", "你好ws2"]
    config = WakeWordConfig(
        wake_words=words,
        threshold=threshold,
        on_wake=on_wake,
    )

    # 检查是否有中文唤醒词
    has_chinese = any(re.search(r'[\u4e00-\u9fff]', w) for w in words)

    if has_chinese:
        # 有中文唤醒词，必须使用 SpeechRecognition
        logger.info("检测到中文唤醒词，使用 SpeechRecognition 检测器")
        return SimpleWakeWordDetector(config)
    elif HAS_OWW and HAS_PYAUDIO and HAS_NUMPY:
        # 纯英文唤醒词，使用 openWakeWord
        logger.info("使用 openWakeWord 检测器")
        return WakeWordDetector(config)
    else:
        logger.info("使用 SpeechRecognition 简易检测器")
        return SimpleWakeWordDetector(config)
