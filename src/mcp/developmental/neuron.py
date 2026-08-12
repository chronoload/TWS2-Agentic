"""神经元类：动态张量生命体

神经元是动态张量生命体——内部权重矩阵 W 的维数随分化/生长/自噬/髓鞘隔离动态变化。
算子 = 权重 = 线性变换矩阵 W（可微调）。
髓鞘是 W 的包裹层（delay/gain/protection），不是额外算子。
seed 给 W 的初始值（先天倾向），使用反馈微调 W 的参数到收敛（后天适应）。
单神经元蕴含处理所有信号的潜能（全息性）。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

import torch
from torch import Tensor


@dataclass
class DimSlice:
    """维度切片：一个信道在神经元中的展开状态

    维度是对偶的——既是输入接口也是输出接口。
    """
    dim_idx: int                    # 维度索引（对应信道偏移）
    size: int                       # 该维度的张量大小
    gain: float = 1.0               # 增益（特化放大时 > 1.0）
    activity: float = 0.0           # 活跃度（自噬依据）
    protection: float = 0.0         # 保护系数（髓鞘庇护）
    myelinated: bool = False        # 是否被髓鞘隔离


@dataclass
class ConvergenceState:
    """收敛状态：三层稳定判定"""
    weight_delta: float = float('inf')    # 权重变化量（< ε 时收敛）
    myelin_stable: bool = False           # 髓鞘拓扑是否稳定
    differentiation_rate: float = float('inf')  # 分化速率（趋零时收敛）

    def is_converged(self, weight_eps: float = 1e-4,
                     diff_threshold: float = 0.01) -> bool:
        """三层都稳定才算收敛"""
        return (self.weight_delta < weight_eps and
                self.myelin_stable and
                self.differentiation_rate < diff_threshold)


class Neuron:
    """动态神经元：权重矩阵 W 维数随分化/生长/自噬/髓鞘隔离动态变化

    单神经元蕴含处理所有信号的潜能（全息性）。
    算子 = 权重 = 线性变换矩阵 W（可微调）。
    髓鞘是 W 的包裹层（delay/gain/protection），不是额外算子。
    seed 给 W 的初始值（先天倾向），使用反馈微调 W 的参数到收敛（后天适应）。
    """

    def __init__(self, seed: int, port_layout: dict[str, tuple[int, int]]):
        """
        Args:
            seed: 生成种子，决定权重的先天倾向
            port_layout: 信道布局 {channel_name: (offset, size)}
        """
        self.seed = seed
        self.port_layout = port_layout
        self.global_dim = sum(s for _, s in port_layout.values())

        # 权重矩阵 W：已展开维度的线性变换
        # 初始为空，随维度展开动态扩张
        self.W: Optional[Tensor] = None
        self.unfolded: dict[str, DimSlice] = {}

        # 神经元级状态
        self.metabolism: float = 0.5
        self.alive: bool = True
        self.parent_seed: Optional[int] = None  # 分化时的父节点 seed

    def unfold(self, channel: str, signal_context: Tensor) -> None:
        """惰性展开维度：W 扩张新行新列

        信号驱动 + 能量阈值过滤：信号在哪些信道有非零分量，就展开哪些维度。
        新行列的初始值由 seed + channel 生成（先天倾向）。
        """
        if channel in self.unfolded or not self.alive:
            return
        offset, size = self.port_layout[channel]

        # 从 seed 生成该维度的初始权重（先天倾向）
        rng = torch.Generator().manual_seed(self.seed + hash(channel) % 2**31)
        new_block = torch.randn(size, size, generator=rng) * 0.1

        if self.W is None:
            self.W = new_block
        else:
            # W 扩张：新增 size 行 size 列
            old_size = self.W.shape[0]
            new_total = old_size + size
            expanded = torch.zeros(new_total, new_total)
            expanded[:old_size, :old_size] = self.W
            expanded[old_size:, old_size:] = new_block
            # 交叉项初始为 0（维度间初始无耦合，由训练建立）
            self.W = expanded

        self.unfolded[channel] = DimSlice(dim_idx=offset, size=size)

    def process(self, signal: Tensor) -> Optional[Tensor]:
        """处理信号：提取已展开维度的切片，经 W 变换

        信号是稠密张量，神经元只关注自己展开的切片。
        未展开的维度切片被忽略。
        """
        if self.W is None or not self.alive:
            return None

        # 提取已展开维度的切片，按展开顺序拼接
        active_indices = []
        for ch, slc in self.unfolded.items():
            active_indices.extend(range(slc.dim_idx, slc.dim_idx + slc.size))

        if not active_indices:
            return None

        signal_slice = signal[active_indices]
        # 应用各维度的 gain（特化放大）
        gains = torch.cat([torch.ones(s.size) * s.gain
                           for s in self.unfolded.values()])
        signal_slice = signal_slice * gains

        # W 变换
        output = self.W @ signal_slice
        # 更新活跃度
        for slc in self.unfolded.values():
            slc.activity += 0.1
        return output

    def adjust_weights(self, signal: Tensor, feedback: float,
                       lr: float = 0.01) -> float:
        """使用反馈微调权重（训练到收敛）

        类似 Oja 规则，但作用在权重矩阵上。
        返回权重变化量（用于收敛判定）。
        """
        if self.W is None:
            return 0.0
        active_indices = []
        for ch, slc in self.unfolded.items():
            active_indices.extend(range(slc.dim_idx, slc.dim_idx + slc.size))
        signal_slice = signal[active_indices]

        # Oja 规则变体：ΔW = lr * feedback * (x⊗y - y⊗y * W)
        y = self.W @ signal_slice
        delta = lr * feedback * (signal_slice.outer(y) - y.outer(y) @ self.W)
        self.W += delta
        return delta.abs().mean().item()

    def replicate(self, signal: Tensor, channels: list[str]) -> 'Neuron':
        """自复制分化：子节点继承维度方向 + 沿信号方向展开 + 特化放大

        子节点的权重由它自己的 seed（变异后）生成初始值，
        继承的是"维度方向"（哪些维度被展开），不是权重参数。
        """
        # seed 变异（遗传多样性）
        child_seed = self.seed + random.randint(1, 2**31 - 1)
        child = Neuron(seed=child_seed, port_layout=self.port_layout)
        child.parent_seed = self.seed

        # 沿信号方向展开维度
        for ch in channels:
            child.unfold(ch, signal)
            # 特化放大：子节点该维度 gain 更高
            if ch in child.unfolded:
                child.unfolded[ch].gain = 1.5
                # 父节点该方向削弱
                if ch in self.unfolded:
                    self.unfolded[ch].gain *= 0.9

        return child

    def autophagy_dims(self, threshold: float = 0.1) -> list[str]:
        """维度级自噬：剪除低活跃维度

        返回被剪除的信道名列表。
        被髓鞘隔离的维度（myelinated=True）受保护，不自噬。
        """
        pruned = []
        for ch in list(self.unfolded.keys()):
            slc = self.unfolded[ch]
            if slc.activity < threshold and not slc.myelinated:
                del self.unfolded[ch]
                pruned.append(ch)
        # 重建 W（移除被剪除维度的行列）
        if pruned:
            self._rebuild_W()
        return pruned

    def _rebuild_W(self) -> None:
        """维度剪除后重建权重矩阵

        注意：W 是按**展开顺序**逐步扩张的（unfold 时新增行列追加到末尾），
        不是按全局 dim_idx 索引的。因此重建时要用**展开顺序的累积偏移**，
        而非 port_layout 中的全局 dim_idx。
        """
        if not self.unfolded:
            self.W = None
            return
        # 按展开顺序计算累积偏移（与 unfold 时的扩张顺序一致）
        active_indices = []
        offset = 0
        for ch, slc in self.unfolded.items():
            active_indices.extend(range(offset, offset + slc.size))
            offset += slc.size
        # 保留 W 中对应行列的子矩阵
        idx = torch.tensor(active_indices)
        self.W = self.W[idx][:, idx]
