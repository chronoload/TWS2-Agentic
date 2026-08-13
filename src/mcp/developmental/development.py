"""发育引擎 — 分化 / 自噬 / 髓鞘强化 / 收敛判据

所有规则基于局部统计量，无反向传播。
新奇性基于覆盖度（find_coverage），不是余弦相似度。
髓鞘是包裹层（thicken_sheath/decay_sheath），不再是 Q 矩阵。
"""
from __future__ import annotations
import torch

from mcp.developmental.neurode import NeuronEcosystem
from mcp.developmental.myelin import MyelinSheathRegistry, ActivationRecord
from mcp.developmental.neuron import ConvergenceState


class DevelopmentEngine:
    """发育引擎：编排分化、自噬、髓鞘强化、收敛判据"""

    def __init__(
        self,
        ecosystem: NeuronEcosystem,
        sheath_registry: MyelinSheathRegistry,
        novelty_threshold: float = 0.7,
        novelty_decay: float = 0.99,
    ):
        self.ecosystem = ecosystem
        self.sheath_registry = sheath_registry
        self.novelty_threshold = novelty_threshold
        self.novelty_decay = novelty_decay
        self._novelty_accumulator = 0.0
        self._differentiation_count = 0
        self._total_signal_count = 0

    def accumulate_novelty(
        self,
        signal: torch.Tensor,
        active_channels: set[str],
    ) -> None:
        """基于覆盖度累积新奇性

        novelty = 1.0 - coverage_score（最佳覆盖度）。
        EWMA 累积。
        """
        _, coverage_score = self.ecosystem.find_coverage(signal, active_channels)
        novelty = 1.0 - coverage_score
        self._novelty_accumulator = (
            self.novelty_decay * self._novelty_accumulator
            + (1 - self.novelty_decay) * novelty
        )
        self._total_signal_count += 1

    def maybe_differentiate(
        self,
        signal: torch.Tensor,
        active_channels: set[str],
    ) -> int:
        """如果新奇性超阈值，触发分化

        调用最佳覆盖神经元的 replicate(signal, channels) 产生子神经元。
        重置新奇性。返回新神经元 idx（未触发返回 -1）。
        """
        if self._novelty_accumulator < self.novelty_threshold:
            return -1
        if self.ecosystem.count() >= self.ecosystem.max_nodes:
            return -1

        # 找最佳覆盖神经元
        best_idx, _ = self.ecosystem.find_coverage(signal, active_channels)
        if best_idx < 0:
            return -1

        parent = self.ecosystem.get_neuron(best_idx)
        if parent is None:
            return -1

        # 调用 replicate 产生子神经元（特化放大 + 父节点削弱）
        child = parent.replicate(signal, list(active_channels))
        idx = self.ecosystem.add_neuron(child)
        if idx < 0:
            return -1

        # 重置新奇性
        self._novelty_accumulator = 0.0
        self._differentiation_count += 1
        return idx

    def maybe_differentiate_joint(
        self,
        signal: torch.Tensor,
        parent_a: int,
        parent_b: int,
        active_channels: set[str],
    ) -> int:
        """联合分化——从两个父节点分化，产生多信号神经元

        子节点继承两个父节点的维度方向。
        """
        if self.ecosystem.count() >= self.ecosystem.max_nodes:
            return -1

        neuron_a = self.ecosystem.get_neuron(parent_a)
        neuron_b = self.ecosystem.get_neuron(parent_b)
        if neuron_a is None or neuron_b is None:
            return -1

        # 合并两个父节点的维度方向 + 信号活跃信道
        combined_channels = (
            set(neuron_a.unfolded.keys())
            | set(neuron_b.unfolded.keys())
            | active_channels
        )

        # 调用 parent_a.replicate 创建子节点（削弱 parent_a 的 gain）
        child = neuron_a.replicate(signal, list(combined_channels))

        # 手动削弱 parent_b 的 gain（replicate 只削弱 parent_a）
        for ch in combined_channels:
            if ch in neuron_b.unfolded:
                neuron_b.unfolded[ch].gain *= 0.9

        idx = self.ecosystem.add_neuron(child)
        if idx < 0:
            return -1

        self._differentiation_count += 1
        return idx

    def autophagy(
        self,
        starvation_threshold: float = 0.01,
        dim_activity_threshold: float = 0.1,
    ) -> dict:
        """自噬——维度级 + 饥饿级 + 髓鞘清理

        返回 {"dims_pruned": {idx: [channels]}, "starved": [indices]}
        """
        # 1. 维度级自噬
        dims_pruned = self.ecosystem.autophagy_dims(threshold=dim_activity_threshold)

        # 2. 饥饿级自噬
        starved = self.ecosystem.autophagy_starvation(
            starvation_threshold=starvation_threshold,
        )

        # 3. 清理死亡神经元的髓鞘
        for idx in starved:
            self.sheath_registry.remove_sheaths_for(idx)

        return {"dims_pruned": dims_pruned, "starved": starved}

    def thicken_myelin_from_coincidence(
        self,
        pairs: list[tuple[ActivationRecord, ActivationRecord]],
    ) -> int:
        """从同时激活对建立/强化髓鞘包裹层

        对每对 (A, ch_a) + (B, ch_b)：
        - 同信道（ch_a == ch_b）→ 增厚或建立髓鞘
        - 不同信道 → 跳过
        返回强化的连接数。
        """
        count = 0
        for A, B in pairs:
            if A.channel != B.channel:
                continue
            # 同信道 → 尝试增厚（强化）
            ok = self.sheath_registry.thicken_sheath(
                A.neuron, A.channel, B.neuron, B.channel)
            if not ok:
                # 髓鞘不存在 → 建立
                self.sheath_registry.add_sheath(
                    A.neuron, A.channel, B.neuron, B.channel)
            count += 1
        return count

    def check_convergence(
        self,
        weight_delta: float,
        myelin_stable: bool,
    ) -> ConvergenceState:
        """返回收敛状态

        differentiation_rate = 本轮分化次数 / 总信号数。
        """
        if self._total_signal_count > 0:
            diff_rate = self._differentiation_count / self._total_signal_count
        else:
            diff_rate = float('inf')
        return ConvergenceState(
            weight_delta=weight_delta,
            myelin_stable=myelin_stable,
            differentiation_rate=diff_rate,
        )
