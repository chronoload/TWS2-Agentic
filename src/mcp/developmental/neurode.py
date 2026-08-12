"""神经元生态 — Neuron 对象容器 + 代谢 + 覆盖度匹配 + 自噬

神经元生态管理 Neuron 对象（dict[int, Neuron]）。
分化 = 新增神经元；自噬 = 维度剪除 / 饥饿清除。
匹配 = 覆盖度（已展开维度与信号非零信道的重合度），替代余弦相似度。
"""
from __future__ import annotations
from typing import Optional
import torch
from mcp.developmental.neuron import Neuron


class NeuronEcosystem:
    """神经元生态：管理 Neuron 对象的容器"""

    def __init__(self, port_layout: dict[str, tuple[int, int]],
                 max_nodes: int = 10000):
        """
        Args:
            port_layout: 信道布局 {channel_name: (offset, size)}
            max_nodes: 最大神经元数
        """
        self.port_layout = port_layout
        self.max_nodes = max_nodes

        # Neuron 对象容器
        self.neurons: dict[int, Neuron] = {}
        self._next_idx = 0

        # 种子神经元（seed=0）
        seed_neuron = Neuron(seed=0, port_layout=port_layout)
        self.neurons[self._next_idx] = seed_neuron
        self._next_idx += 1

        # 代谢参数
        self._metabolism_increment = 0.1
        self._metabolism_decay = 0.95

    def count(self) -> int:
        """存活神经元数"""
        return sum(1 for n in self.neurons.values() if n.alive)

    def add_neuron(self, neuron: Neuron) -> int:
        """添加神经元对象，返回索引"""
        if self.count() >= self.max_nodes:
            return -1
        idx = self._next_idx
        self.neurons[idx] = neuron
        self._next_idx += 1
        return idx

    def get_neuron(self, idx: int) -> Optional[Neuron]:
        """获取神经元"""
        return self.neurons.get(idx)

    def get_active_indices(self) -> list[int]:
        """获取存活神经元索引"""
        return [i for i, n in self.neurons.items() if n.alive]

    def kill(self, idx: int) -> None:
        """标记神经元死亡"""
        if idx in self.neurons:
            self.neurons[idx].alive = False

    def tick_metabolism(self, active_indices: list[int]) -> None:
        """代谢更新：活跃神经元升高，不活跃的衰减"""
        active_set = set(active_indices)
        for i, n in self.neurons.items():
            if not n.alive:
                continue
            if i in active_set:
                n.metabolism = min(1.0, n.metabolism + self._metabolism_increment)
            else:
                n.metabolism *= self._metabolism_decay
            # 钳制下界
            n.metabolism = max(0.0, n.metabolism)

    def find_coverage(self, signal: torch.Tensor,
                      active_channels: set[str]) -> tuple[int, float]:
        """覆盖度匹配——找已展开维度与信号非零信道重合度最高的神经元

        coverage_score = 重合信道数 / 信号非零信道数
        完全覆盖时 coverage=1.0。
        """
        if not active_channels:
            return -1, 0.0

        best_idx = -1
        best_score = -1.0
        for idx in self.get_active_indices():
            neuron = self.neurons[idx]
            unfolded_channels = set(neuron.unfolded.keys())
            overlap = len(unfolded_channels & active_channels)
            score = overlap / len(active_channels)
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx == -1:
            return -1, 0.0
        return best_idx, best_score

    def autophagy_dims(self, threshold: float = 0.1) -> dict[int, list[str]]:
        """维度级自噬——对所有存活神经元调用 neuron.autophagy_dims

        返回 {neuron_idx: [pruned_channels]}
        """
        result: dict[int, list[str]] = {}
        for idx, neuron in self.neurons.items():
            if not neuron.alive:
                continue
            pruned = neuron.autophagy_dims(threshold)
            if pruned:
                result[idx] = pruned
        return result

    def autophagy_starvation(self, starvation_threshold: float = 0.01,
                             protection_threshold: float = 0.1) -> list[int]:
        """饥饿自噬——代谢低于阈值且保护系数低的神经元被 kill

        保护系数取神经元已展开维度的最大 protection（髓鞘庇护）。
        返回被杀的索引列表。
        """
        killed: list[int] = []
        for idx, neuron in self.neurons.items():
            if not neuron.alive:
                continue
            if neuron.metabolism < starvation_threshold:
                # 神经元保护系数 = 已展开维度的最大 protection
                if neuron.unfolded:
                    max_protection = max(
                        s.protection for s in neuron.unfolded.values())
                else:
                    max_protection = 0.0
                if max_protection < protection_threshold:
                    neuron.alive = False
                    killed.append(idx)
        return killed
