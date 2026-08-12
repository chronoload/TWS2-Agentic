"""Layer 5: 高层脑 — 始终活跃的可塑发育层

核心职责：
1. process(): 介入输入信号化（始终活跃）——用 find_coverage 做覆盖度匹配，
   记录激活到 CoincidenceDetector，检测同时激活对并建立髓鞘。
2. compute_lambda(): 连续干预强度 λ ∈ [0,1]（高/低/中区间 + 非语言模态 λ=1.0 + sleep λ=lambda_sleep）。
3. intervene(): 残差修正 y = (1-λ)·y_reflex + λ·y_higher；高层输出 y_higher 来源：
   用 SignalDispatcher 并行分发信号，收集触发事件作为高层输出。
4. dispatch_signal() / resolve_triggers(): 委托 SignalDispatcher 做事件驱动并行分发
   （时序竞争 + 重合窗口跨模态绑定）。
5. learn_from_intervention_delta(): 从干预差异学习——对被干预神经元 adjust_weights 微调权重到收敛。
6. record_for_dream(): 记录 4 元组供做梦学习。

核心变更（相比旧实现）：
- propagate_signal（softmax 随机游走）→ dispatch_signal（事件驱动并行分发）
- match（余弦相似度）→ find_coverage（覆盖度匹配）
- myelin.update（Q 矩阵更新）→ sheath_registry.thicken_sheath + CoincidenceDetector 追溯源
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
import torch

from mcp.developmental.signal import Signal
from mcp.developmental.neurode import NeuronEcosystem
from mcp.developmental.myelin import (
    MyelinSheathRegistry,
    CoincidenceDetector,
    SignalDispatcher,
    SignalEvent,
)
from mcp.developmental.development import DevelopmentEngine


class HigherBrain(ABC):
    """高层脑抽象基类 — 用户可替换发育策略"""

    @abstractmethod
    def process(self, input_signals: dict[str, Signal]) -> dict[str, Any]:
        """介入输入信号化（始终活跃）：find_coverage 匹配 + 记录激活 + 建立髓鞘"""
        pass

    @abstractmethod
    def compute_lambda(self, match_result: dict) -> float:
        """计算连续干预强度 λ ∈ [0,1]"""
        pass

    @abstractmethod
    def intervene(
        self,
        raw_outputs: dict[str, Signal],
        match_result: dict[str, Any],
    ) -> dict[str, Signal]:
        """介入输出处理（连续 λ 残差修正）：y = (1-λ)·y_reflex + λ·y_higher"""
        pass

    @abstractmethod
    def dispatch_signal(
        self, signal: torch.Tensor, source_tag: str
    ) -> list[SignalEvent]:
        """事件驱动并行分发：委托 SignalDispatcher.dispatch"""
        pass

    @abstractmethod
    def resolve_triggers(
        self,
        events: list[SignalEvent],
        threshold: float,
        coincidence_window: float,
    ) -> list[SignalEvent]:
        """解析触发：时序竞争 + 重合窗口跨模态绑定"""
        pass

    @abstractmethod
    def learn_from_intervention_delta(
        self,
        reflex_outputs: dict[str, Signal],
        final_outputs: dict[str, Signal],
    ) -> None:
        """从干预差异学习——微调被干预神经元的权重"""
        pass

    @abstractmethod
    def get_confidence(self) -> float:
        """获取最近一次匹配的置信度"""
        pass

    @abstractmethod
    def record_for_dream(
        self,
        input_signals: dict[str, Signal],
        reflex_outputs: dict[str, Signal],
        final_outputs: dict[str, Signal],
        match_result: dict[str, Any],
    ) -> None:
        """记录 4 元组到轨迹日志供做梦学习"""
        pass


class DefaultHigherBrain(HigherBrain):
    """默认实现：始终介入 + 连续 λ 残差干预 + 事件驱动并行分发 + 维度级处理 + 权重微调"""

    def __init__(
        self,
        port_layout: dict[str, tuple[int, int]],
        max_nodes: int = 10000,
        llm_scorer=None,
        llm_topk: int = 20,
        theta_high: float = 0.8,
        theta_low: float = 0.2,
        lambda_high: float = 0.9,
        lambda_low: float = 0.7,
        lambda_mid: float = 0.2,
        lambda_sleep: float = 0.1,
        coincidence_retention: float = 1.0,
    ):
        self.port_layout = port_layout
        self.global_dim = sum(s for _, s in port_layout.values())
        # 核心组件
        self.ecosystem = NeuronEcosystem(
            port_layout=port_layout, max_nodes=max_nodes
        )
        self.sheath_registry = MyelinSheathRegistry()
        self.engine = DevelopmentEngine(self.ecosystem, self.sheath_registry)
        self.coincidence = CoincidenceDetector(retention=coincidence_retention)
        # SignalDispatcher 持有 ecosystem.neurons 与 sheath_registry._sheaths 的同一引用，
        # 新增神经元/髓鞘时自动可见（dict 按引用传递）
        self.dispatcher = SignalDispatcher(
            self.ecosystem.neurons, self.sheath_registry._sheaths
        )
        # 可选 LLM 预筛（新匹配用 find_coverage，LLM 预筛保留接口供未来扩展）
        self.llm_scorer = llm_scorer
        self.llm_topk = llm_topk
        # 接管判定阈值
        self.theta_high = theta_high
        self.theta_low = theta_low
        # 连续 λ 参数
        self.lambda_high = lambda_high
        self.lambda_low = lambda_low
        self.lambda_mid = lambda_mid
        self.lambda_sleep = lambda_sleep
        # 状态
        self._last_confidence = 0.0
        self._last_lambda = 0.0
        self._trajectory: list[int] = []
        self._trajectory_log: list[tuple] = []  # 做梦学习 4 元组日志

    def process(self, input_signals: dict[str, Signal]) -> dict[str, Any]:
        """介入输入信号化（始终活跃）

        (a) 调用 ecosystem.find_coverage 找最佳覆盖神经元（覆盖度匹配，替代余弦相似度）
        (b) 对每个信道信号记录激活到 CoincidenceDetector（追溯激活源）
        (c) 检测同时激活对，调用 engine.thicken_myelin_from_coincidence 建立髓鞘
        """
        active_channels = set(input_signals.keys())
        # (a) 覆盖度匹配——find_coverage 实际只用 active_channels 计算重合度
        global_signal = torch.zeros(self.global_dim)
        winner_id, coverage_score = self.ecosystem.find_coverage(
            global_signal, active_channels
        )

        # (b) 对每个信道信号记录激活（所有覆盖该信道的神经元均记录，追溯激活源）
        t = 0.0
        for ch_name, sig in input_signals.items():
            source_tag = sig.metadata.get("source_tag", "default")
            for idx in self.ecosystem.get_active_indices():
                neuron = self.ecosystem.get_neuron(idx)
                if neuron is not None and ch_name in neuron.unfolded:
                    self.coincidence.record(idx, ch_name, source_tag, t)

        # (c) 检测同时激活对，建立髓鞘（同源同信道不同神经元 → sheath_registry 增厚/建立）
        pairs = self.coincidence.find_coincident_pairs()
        if pairs:
            self.engine.thicken_myelin_from_coincidence(pairs)

        # 记录轨迹
        if winner_id >= 0:
            self._trajectory.append(winner_id)
            if len(self._trajectory) > 100:
                self._trajectory.pop(0)

        self._last_confidence = coverage_score

        # 检测非语言模态（供 compute_lambda 判定 λ=1.0）
        has_non_language = any(
            not s.mime_type.startswith("text/") for s in input_signals.values()
        )
        return {
            "winner_id": winner_id,
            "confidence": coverage_score,
            "coverage_score": coverage_score,
            "active_channels": list(active_channels),
            "trajectory": list(self._trajectory),
            "non_language": has_non_language,
        }

    def compute_lambda(self, match_result: dict) -> float:
        """计算连续干预强度 λ ∈ [0,1]

        间歇替代模型：高层脑始终在干扰，强度连续可变。
        y = (1-λ)·y_reflex + λ·y_higher

        - 高置信度（≥theta_high）：已掌握 → λ=lambda_high（接近完全接管）
        - 低置信度（≤theta_low）：完全陌生，自主探索/分化 → λ=lambda_low
        - 中区间：反射弧示范为主 → λ 整体偏低（≤ lambda_mid + 0.1）
        - 非语言模态：LLM 本就不介入 → λ=1.0（高层完全接管）
        - 睡眠态：压低至 lambda_sleep（弱响应，非完全切断）
        """
        confidence = match_result.get("confidence", 0.0)
        # 睡眠态优先：压低 λ（运动弛缓对所有模态生效，对应睡眠时的肌张力丧失）
        is_sleep = match_result.get("sleep_mode", False)
        if is_sleep:
            lam = self.lambda_sleep
            self._last_lambda = lam
            return lam
        # 胚胎期保底：winner 神经元 W=None（未展开维度）→ 高层无法处理 → λ=0
        # 对应"反射弧自完备"——高层脑未发育时反射弧保底输出
        winner_id = match_result.get("winner_id", -1)
        if winner_id >= 0:
            neuron = self.ecosystem.get_neuron(winner_id)
            if neuron is None or neuron.W is None:
                self._last_lambda = 0.0
                return 0.0
        # 非语言模态判定
        is_non_language = match_result.get("non_language", False)
        if is_non_language:
            self._last_lambda = 1.0
            return 1.0
        if confidence >= self.theta_high:
            lam = self.lambda_high
        elif confidence <= self.theta_low:
            lam = self.lambda_low
        else:
            # 中区间线性插值，但整体偏低
            ratio = (confidence - self.theta_low) / (
                self.theta_high - self.theta_low
            )
            lam = self.lambda_low + ratio * (
                self.lambda_high - self.lambda_low
            )
            lam = min(lam, self.lambda_mid + 0.1)
        self._last_lambda = lam
        return lam

    def intervene(
        self,
        raw_outputs: dict[str, Signal],
        match_result: dict[str, Any],
    ) -> dict[str, Signal]:
        """介入输出处理（连续 λ 残差修正）

        y = (1-λ)·y_reflex + λ·y_higher

        高层输出 y_higher 来源：用 dispatcher 并行分发信号，
        收集触发事件作为高层输出（事件驱动并行分发，各维度同时经各自算子传输）。
        """
        lam = self.compute_lambda(match_result)
        if lam <= 0.0:
            return dict(raw_outputs)
        if lam >= 1.0 and not raw_outputs:
            return {}

        final: dict[str, Signal] = {}
        for key, reflex_sig in raw_outputs.items():
            higher_data = self._generate_higher_output(reflex_sig, match_result)
            blended = (1.0 - lam) * reflex_sig.data + lam * higher_data
            final[key] = Signal(
                data=blended,
                mime_type=reflex_sig.mime_type,
                metadata={
                    **reflex_sig.metadata,
                    "lambda": lam,
                    "intervened": True,
                },
            )
        return final

    def _generate_higher_output(
        self,
        reflex_sig: Signal,
        match_result: dict[str, Any],
    ) -> torch.Tensor:
        """生成高层输出 y_higher——用 dispatcher 并行分发信号，收集触发事件

        各维度切片同时经各自算子（W）传输，髓鞘包裹层（delay/gain）调制传输特性。
        """
        # 事件驱动并行分发
        events = self.dispatch_signal(reflex_sig.data, source_tag="higher")
        if not events:
            # 无事件（无髓鞘连接）：胚胎期注入小噪声（探索性驱动）
            return reflex_sig.data + torch.randn_like(reflex_sig.data) * 0.05

        # 解析触发：时序竞争 + 重合窗口跨模态叠加
        triggered = self.resolve_triggers(
            events, threshold=0.01, coincidence_window=0.1
        )
        if triggered:
            # 合并所有触发事件的数据
            higher = sum(e.data for e in triggered)
        else:
            # 无事件超阈值：取最强事件
            higher = max(events, key=lambda e: e.data.norm().item()).data

        # 对齐到 reflex_sig.data 的形状
        if higher.numel() >= reflex_sig.data.numel():
            return higher[: reflex_sig.data.numel()].clone()
        padded = torch.zeros_like(reflex_sig.data)
        padded[: higher.numel()] = higher
        return padded

    def dispatch_signal(
        self, signal: torch.Tensor, source_tag: str
    ) -> list[SignalEvent]:
        """事件驱动并行分发——委托给 SignalDispatcher.dispatch

        信号各维度分量同时经各自算子传输（并行性从维度对偶性自然涌现）。
        每次分发前清空事件队列，避免历史事件累积。
        """
        self.dispatcher.event_queue = []  # 清空队列
        return self.dispatcher.dispatch(signal, source_tag)

    def resolve_triggers(
        self,
        events: list[SignalEvent],
        threshold: float,
        coincidence_window: float,
    ) -> list[SignalEvent]:
        """解析触发——委托给 SignalDispatcher.resolve_triggers

        - 第一个到达阈值的赢（时序竞争）
        - 时间差 < 重合窗口的多信号叠加触发（跨模态绑定）
        """
        # 按到达时间排序后注入 dispatcher 队列
        self.dispatcher.event_queue = sorted(
            events, key=lambda e: e.arrival_time
        )
        return self.dispatcher.resolve_triggers(threshold, coincidence_window)

    def learn_from_intervention_delta(
        self,
        reflex_outputs: dict[str, Signal],
        final_outputs: dict[str, Signal],
    ) -> None:
        """从干预差异学习——对被干预的神经元调用 adjust_weights 微调权重到收敛

        差异越大，反馈越强，权重调整幅度越大。迭代到权重变化量 < ε 收敛。
        """
        if not self._trajectory:
            return
        winner_id = self._trajectory[-1]
        neuron = self.ecosystem.get_neuron(winner_id)
        if neuron is None or neuron.W is None:
            return

        for key in final_outputs:
            if key not in reflex_outputs:
                continue
            reflex_sig = reflex_outputs[key]
            final_sig = final_outputs[key]
            # 干预差异作为反馈信号
            diff = final_sig.data - reflex_sig.data
            feedback = diff.abs().mean().item()
            if feedback < 1e-6:
                continue
            # 微调权重到收敛
            for _ in range(100):
                delta = neuron.adjust_weights(reflex_sig.data, feedback)
                if delta < 1e-4:
                    break

    def get_confidence(self) -> float:
        """返回最近一次 match 的 confidence"""
        return self._last_confidence

    def record_for_dream(
        self,
        input_signals: dict[str, Signal],
        reflex_outputs: dict[str, Signal],
        final_outputs: dict[str, Signal],
        match_result: dict[str, Any],
    ) -> None:
        """记录 4 元组到 _trajectory_log 供做梦学习"""
        self._trajectory_log.append(
            (input_signals, reflex_outputs, final_outputs, match_result)
        )
