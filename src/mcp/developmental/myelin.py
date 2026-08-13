"""髓鞘包裹层 + 维度间算子连接 + 追溯激活源同时检测

核心概念：
- 髓鞘不是标量 Q 矩阵，而是算子（权重 W）的包裹层（delay/gain/protection）。
- 连接 = 维度间算子（W，由神经元管理）+ 髓鞘包裹层（本模块管理）。
- 算子连接通过追溯激活源建立（同源同信道 → 建立连接），不是 Hebbian 同时激活。
"""
from __future__ import annotations

from dataclasses import dataclass
from torch import Tensor


@dataclass
class MyelinSheath:
    """髓鞘：权重算子的包裹层，优化传输特性

    髓鞘不改变算子（W）本身，只改变传输特性：
    - delay: 传导延迟，增厚→延迟↓
    - gain: 信号增益，增厚→增益↑
    - protection: 保护系数，防止算子被自噬

    连接 = 维度间算子（W）+ 髓鞘包裹层（delay/gain/protection）。
    "多出的算子是髓鞘"——髓鞘是算子外的包裹，不是额外算子。
    """
    src_neuron: int
    src_channel: str
    dst_neuron: int
    dst_channel: str
    delay: float = 1.0
    gain: float = 1.0
    protection: float = 0.0

    def thicken(self, amount: float = 0.05) -> None:
        """髓鞘增厚：delay↓, gain↑, protection↑"""
        self.delay = max(0.1, self.delay - amount * 0.5)
        self.gain = min(2.0, self.gain + amount)
        self.protection = min(1.0, self.protection + amount * 0.3)

    def decay(self, amount: float = 0.05) -> None:
        """髓鞘衰减：delay↑, gain↓

        protection 不随使用衰减，只在稳态缩放时调整。
        """
        self.delay += amount * 0.5
        self.gain = max(0.1, self.gain - amount)


@dataclass
class ActivationRecord:
    """激活记录：神经元某维度被激活时记录

    用于追溯激活源——source_tag 标识信号来源，
    同源同信道的不同神经元激活 → 候选算子连接。
    """
    neuron: int
    channel: str       # 被激活的信道
    source_tag: str    # 激活源标识（信号ID）
    timestamp: float


class CoincidenceDetector:
    """同时激活检测器：通过追溯源判定算子连接建立

    不是时间窗口 hack，是因果判定：
    - 同源（同一信号导致）+ 同信道（维度对应）→ 建立算子连接
    - 反复同源同信道 → 算子强化（髓鞘化）
    - 长期不同源 → 算子衰减

    先有维度共振（同维度神经元天然弱耦合），
    同时激活 → 建立 W 交叉项 → 髓鞘化 → 强连接。
    """

    def __init__(self, retention: float = 1.0):
        self.recent: list[ActivationRecord] = []
        self.retention = retention

    def record(self, neuron: int, channel: str, source_tag: str, t: float) -> None:
        """记录一次激活，并清理超过保留窗口的旧记录"""
        self.recent.append(ActivationRecord(neuron, channel, source_tag, t))
        self.recent = [r for r in self.recent if t - r.timestamp < self.retention]

    def find_coincident_pairs(self) -> list[tuple[ActivationRecord, ActivationRecord]]:
        """找出同源同信道的激活对 → 候选算子连接

        同源（source_tag 相同）+ 同信道（channel 相同）→ 建立连接。
        不同神经元，同源同信道 → 该信道上有算子。
        """
        pairs = []
        groups: dict[tuple[str, str], list[ActivationRecord]] = {}
        for r in self.recent:
            key = (r.source_tag, r.channel)
            groups.setdefault(key, []).append(r)
        for records in groups.values():
            for i in range(len(records)):
                for j in range(i + 1, len(records)):
                    if records[i].neuron != records[j].neuron:
                        pairs.append((records[i], records[j]))
        return pairs


class MyelinSheathRegistry:
    """髓鞘包裹层注册表：管理所有神经元间的髓鞘连接

    键为 (src_neuron, src_channel, dst_neuron, dst_channel)，
    值为 MyelinSheath。提供按神经元/信道的查询、稳态缩放、路径级增厚/衰减。

    髓鞘是算子的包裹层，不是额外算子——本注册表只管理包裹层的传输特性，
    算子本身（权重 W）由神经元管理。
    """

    def __init__(self):
        self._sheaths: dict[tuple[int, str, int, str], MyelinSheath] = {}

    def add_sheath(
        self,
        src_neuron: int,
        src_channel: str,
        dst_neuron: int,
        dst_channel: str,
        delay: float = 1.0,
        gain: float = 1.0,
        protection: float = 0.0,
    ) -> MyelinSheath:
        """新增一条髓鞘包裹层（若已存在则覆盖）"""
        key = (src_neuron, src_channel, dst_neuron, dst_channel)
        sheath = MyelinSheath(
            src_neuron=src_neuron,
            src_channel=src_channel,
            dst_neuron=dst_neuron,
            dst_channel=dst_channel,
            delay=delay,
            gain=gain,
            protection=protection,
        )
        self._sheaths[key] = sheath
        return sheath

    def get_sheath(
        self,
        src_neuron: int,
        src_channel: str,
        dst_neuron: int,
        dst_channel: str,
    ) -> MyelinSheath | None:
        """读取单条髓鞘，不存在返回 None"""
        return self._sheaths.get((src_neuron, src_channel, dst_neuron, dst_channel))

    def get_sheaths_from(self, neuron: int, channel: str) -> list[MyelinSheath]:
        """查询从某神经元某信道出发的所有髓鞘（出边）

        供 SignalDispatcher 沿信道并行分发信号用。
        """
        return [
            s for s in self._sheaths.values()
            if s.src_neuron == neuron and s.src_channel == channel
        ]

    def remove_sheaths_for(self, neuron: int) -> int:
        """删除涉及某神经元（作为源或目标）的所有髓鞘

        用于神经元被自噬时清理其全部连接。返回删除条数。
        """
        keys_to_remove = [
            k for k, s in self._sheaths.items()
            if s.src_neuron == neuron or s.dst_neuron == neuron
        ]
        for k in keys_to_remove:
            del self._sheaths[k]
        return len(keys_to_remove)

    def homeostatic_scale(self, beta: float = 0.1) -> None:
        """稳态缩放（突触稳态假说，sleep NREM S3 相位）

        按保护系数加权衰减 gain：
            gain' = gain · (1 - beta · (1 - protection))

        保护系数高的髓鞘几乎不衰减（核心层，对应冻结主干）
        保护系数低的髓鞘正常衰减（活跃层，对应可变残差）

        相对强弱保持，绝对强度下降，清理噪声 + 重置学习容量。
        protection 不变（只由 thicken/路径强化调整）。
        """
        for sheath in self._sheaths.values():
            decay_rate = beta * (1.0 - sheath.protection)
            sheath.gain = sheath.gain * (1.0 - decay_rate)

    def thicken_sheath(
        self,
        src_neuron: int,
        src_channel: str,
        dst_neuron: int,
        dst_channel: str,
        amount: float = 0.05,
    ) -> bool:
        """路径级操作：增厚指定髓鞘（髓鞘化）。返回是否成功命中。

        用于做梦学习的生成重放（NREM S2）和前向预演（REM Preplay）。
        """
        sheath = self.get_sheath(src_neuron, src_channel, dst_neuron, dst_channel)
        if sheath is None:
            return False
        sheath.thicken(amount)
        return True

    def decay_sheath(
        self,
        src_neuron: int,
        src_channel: str,
        dst_neuron: int,
        dst_channel: str,
        amount: float = 0.05,
    ) -> bool:
        """路径级操作：衰减指定髓鞘。返回是否成功命中。

        用于做梦学习的前向预演中预测与实际不一致时。
        """
        sheath = self.get_sheath(src_neuron, src_channel, dst_neuron, dst_channel)
        if sheath is None:
            return False
        sheath.decay(amount)
        return True


@dataclass
class SignalEvent:
    """信号事件：信号在某时刻到达某神经元的某信道

    事件驱动并行分发的最小单位——各信道分量同时经各自算子传输，
    到达目标神经元时生成一个事件。
    """
    arrival_time: float
    target_neuron: int
    channel: str
    data: Tensor               # 该信道的信号分量
    source_tag: str            # 激活源标识
    origin_neuron: int         # 起源神经元（-1=外部信号）


class SignalDispatcher:
    """信号分发器：事件驱动并行传输

    信号各维度分量同时经各自算子传输——并行性从维度对偶性自然涌现。
    不是"顺序游走选一条路"，是"各维度同时走各自的算子"。

    时序竞争 + 重合窗口：
    - 第一个到达阈值的赢（时序竞争）
    - 时间差 < 重合窗口的多信号会叠加触发（跨模态绑定）
    """

    def __init__(self, neurons: dict[int, "Neuron"],
                 sheaths: dict[tuple[int, str, int, str], MyelinSheath]):
        self.neurons = neurons
        self.sheaths = sheaths
        self.event_queue: list[SignalEvent] = []

    def dispatch(self, signal: Tensor, source_tag: str,
                 t: float = 0.0) -> list[SignalEvent]:
        """并行分发信号：各信道同时经各自算子传输

        从所有激活的神经元分发，沿每个已展开信道查找髓鞘连接，
        传输（应用算子 + 髓鞘 delay/gain），按到达时间排序返回。
        """
        # 从所有激活的神经元分发
        for nid, neuron in self.neurons.items():
            if not neuron.alive or neuron.W is None:
                continue
            # 神经元处理信号（各维度切片经 W 变换）
            output = neuron.process(signal)
            if output is None:
                continue

            # 沿每个已展开信道分发（并行）
            for ch in neuron.unfolded:
                # 查找该信道上的所有髓鞘连接
                for (src_n, src_ch, dst_n, dst_ch), sheath in self.sheaths.items():
                    if src_n == nid and src_ch == ch:
                        # 传输：应用算子（已在 output 中）+ 髓鞘（delay/gain）
                        arrival = t + sheath.delay
                        transmitted = output * sheath.gain
                        event = SignalEvent(
                            arrival_time=arrival,
                            target_neuron=dst_n,
                            channel=dst_ch,
                            data=transmitted,
                            source_tag=source_tag,
                            origin_neuron=nid,
                        )
                        self.event_queue.append(event)

        # 按到达时间排序（时序竞争基础）
        self.event_queue.sort(key=lambda e: e.arrival_time)
        return self.event_queue

    def resolve_triggers(self, threshold: float,
                         coincidence_window: float) -> list[SignalEvent]:
        """解析触发：时序竞争 + 重合窗口

        - 第一个到达阈值的赢（时序竞争）：强度低于阈值的事件被过滤
        - 时间差 < 重合窗口的多信号叠加触发（跨模态绑定）：
          同一神经元在窗口内收到多信道信号时叠加
        """
        triggered = []
        used = set()

        for i, event in enumerate(self.event_queue):
            if i in used:
                continue
            strength = event.data.norm().item()
            if strength < threshold:
                continue

            # 检查重合窗口内的其他事件（跨模态叠加）
            combined = event.data.clone()
            for j in range(i + 1, len(self.event_queue)):
                if j in used:
                    continue
                other = self.event_queue[j]
                if other.arrival_time - event.arrival_time > coincidence_window:
                    break  # 已按到达时间排序，后续都超窗口
                if other.target_neuron == event.target_neuron:
                    # 同一神经元的另一信道信号叠加（跨模态绑定）
                    combined += other.data
                    used.add(j)

            triggered.append(SignalEvent(
                arrival_time=event.arrival_time,
                target_neuron=event.target_neuron,
                channel=event.channel,
                data=combined,
                source_tag=event.source_tag,
                origin_neuron=event.origin_neuron,
            ))
            used.add(i)

        return triggered
