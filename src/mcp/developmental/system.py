"""DevelopmentalSystem — 发育智能系统主循环

双模主循环（以 port_layout 构造）：
  觉醒态（AWAKE）：读取入端口 → 高层脑 process 介入 → 反射弧 → 高层脑 intervene
                  → 事件驱动 dispatch_signal 强化路径 → 写出端口 → 记录 4 元组
                  → 累积新奇性 → 可能分化
  睡眠态（SLEEP）：四相位做梦学习（sheath_registry 操作，无梯度）
                  + 睡眠感觉敏感性（外界输入注入 + lambda_sleep 压低）

核心变更（相比旧实现）：
- myelin.* → sheath_registry.*（homeostatic_scale / thicken_sheath / decay_sheath）
- propagate_signal / simulate_internally → dispatch_signal（事件驱动并行分发）
- myelin._edges → sheath_registry._sheaths（统计髓鞘数）
- global_dim 构造 → port_layout 构造
- higher_brain.learn → engine.accumulate_novelty + maybe_differentiate + 事件驱动 sheath 强化
- 新增 check_convergence 收敛判据集成
"""
from __future__ import annotations
import json
import os
import torch
from enum import Enum
from typing import Any, Optional

from mcp.developmental.signal import Signal
from mcp.developmental.port import PortRegistry, InputPort, OutputPort
from mcp.developmental.reptilian import ReptilianKernel
from mcp.developmental.route import Route, RouteExecutor
from mcp.developmental.reflex import ReflexArc
from mcp.developmental.higher_brain import DefaultHigherBrain
from mcp.developmental.neuron import ConvergenceState


class SystemMode(Enum):
    """系统模式：觉醒 / 睡眠"""
    AWAKE = "awake"
    SLEEP = "sleep"


class DevelopmentalSystem:
    """发育智能系统主循环（觉醒/睡眠双模 + 四相位做梦学习 + 事件驱动）"""

    def __init__(
        self,
        port_layout: dict[str, tuple[int, int]],
        max_nodes: int = 10000,
    ):
        """
        Args:
            port_layout: 信道布局 {channel_name: (offset, size)}
            max_nodes: 最大神经元数
        """
        self.port_layout = port_layout
        self.global_dim = sum(s for _, s in port_layout.values())

        # 核心组件装配
        self.ports = PortRegistry()
        self.reptile = ReptilianKernel()
        self.routes: list[Route] = []
        self.reflex = ReflexArc(kernel=self.reptile)
        self.higher_brain = DefaultHigherBrain(
            port_layout=port_layout, max_nodes=max_nodes
        )
        self.executor = RouteExecutor(self.reptile)

        # 发育状态
        self.phase = "embryonic"  # embryonic | exploratory | mature
        self.mode = SystemMode.AWAKE
        self.step_count = 0

        # 觉醒轨迹日志（供睡眠态重放）
        # 每条记录：4 元组 (input_signals, reflex_outputs, final_outputs, match_result)
        # reflex_outputs 与 final_outputs 的差异 = 反事实素材
        self._trajectory_log: list[tuple[dict, dict, dict, dict]] = []

        # 做梦学习参数
        self.sleep_beta = 0.1              # 稳态缩放强度
        self.sleep_preplay_consistency = 0.5  # 前向预演一致性阈值

    def add_route(self, route: Route) -> None:
        """添加路由（兼容 RouteExecutor 接口）"""
        self.routes.append(route)
        self.executor.add_route(route)

    def _read_input_ports(self) -> dict[str, Signal]:
        """读取所有入端口，用 port name 作为键（无 name 时用 port_id）"""
        input_signals: dict[str, Signal] = {}
        # 反向映射：port_id → name
        id_to_name = {pid: name for name, pid in self.ports._names.items()}
        for port_id, port in self.ports._ports.items():
            if not isinstance(port, InputPort):
                continue
            try:
                sig = port.get_signal()
            except Exception:
                continue
            if sig is not None:
                key = id_to_name.get(port_id, port_id)
                input_signals[key] = sig
        return input_signals

    def _write_output_ports(self, outputs: dict[str, Signal]) -> None:
        """写入所有出端口"""
        for port in self.ports.get_output_ports():
            for key, signal in outputs.items():
                if signal.mime_type in port.get_accepted_types():
                    try:
                        port.put_signal(signal)
                    except (TypeError, RuntimeError):
                        pass

    def _combine_signals(self, input_signals: dict[str, Signal]) -> Signal:
        """合并多信道信号为全局张量（按 port_layout 偏移拼接）"""
        global_vec = torch.zeros(self.global_dim)
        for ch_name, sig in input_signals.items():
            if ch_name in self.port_layout:
                offset, size = self.port_layout[ch_name]
                data = sig.data.flatten()[:size]
                global_vec[offset:offset + data.numel()] = data
        return Signal(
            data=global_vec,
            mime_type="multi/channel",
            metadata={"step": self.step_count},
        )

    def _reinforce_path_via_sheaths(
        self, path: list[int], amount: float = 0.02
    ) -> int:
        """沿路径增厚髓鞘（用 sheath_registry.thicken_sheath）

        对路径中每对相邻神经元，找到连接它们的髓鞘并增厚。
        返回增厚的髓鞘数。
        """
        sheath_reg = self.higher_brain.sheath_registry
        count = 0
        for i in range(len(path) - 1):
            src, dst = path[i], path[i + 1]
            for key in list(sheath_reg._sheaths.keys()):
                if key[0] == src and key[2] == dst:
                    if sheath_reg.thicken_sheath(*key, amount=amount):
                        count += 1
        return count

    def _decay_path_via_sheaths(
        self, path: list[int], amount: float = 0.02
    ) -> int:
        """沿路径衰减髓鞘（用 sheath_registry.decay_sheath）

        对路径中每对相邻神经元，找到连接它们的髓鞘并衰减。
        返回衰减的髓鞘数。
        """
        sheath_reg = self.higher_brain.sheath_registry
        count = 0
        for i in range(len(path) - 1):
            src, dst = path[i], path[i + 1]
            for key in list(sheath_reg._sheaths.keys()):
                if key[0] == src and key[2] == dst:
                    if sheath_reg.decay_sheath(*key, amount=amount):
                        count += 1
        return count

    def step_awake(
        self,
        external_inputs: Optional[dict[str, Signal]] = None,
    ) -> dict[str, Any]:
        """觉醒态单步运行（事件驱动主循环）

        流程：
        1. 读取入端口（或用 external_inputs）
        2. 高层脑 process() 介入输入信号化（始终活跃）
        3. 反射弧 execute() 产生原始输出
        4. 高层脑 intervene() 连续 λ 残差修正（失败时反射弧保底）
        5. 事件驱动：dispatch_signal 分发组合信号 → resolve_triggers → 沿触发路径 thicken_sheath
        6. 写出端口
        7. 记录 4 元组到 _trajectory_log（反事实素材）
        8. engine.accumulate_novelty 累积新奇性
        9. engine.maybe_differentiate 可能分化

        返回 {outputs, match_result, lambda, differentiated, ...}
        """
        self.step_count += 1
        self.mode = SystemMode.AWAKE

        # 1. 读取入端口（或用 external_inputs）
        input_signals = (
            external_inputs if external_inputs is not None
            else self._read_input_ports()
        )
        if not input_signals:
            return {
                "outputs": {},
                "match_result": {},
                "lambda": 0.0,
                "differentiated": -1,
            }

        # 胚胎期：向输入注入小噪声（探索性驱动）
        if self.phase == "embryonic":
            noisy_signals = {}
            for key, sig in input_signals.items():
                noisy_data = sig.data + torch.randn_like(sig.data) * 0.01
                noisy_signals[key] = Signal(
                    data=noisy_data,
                    mime_type=sig.mime_type,
                    metadata={**sig.metadata, "noisy": True},
                )
            input_signals = noisy_signals

        # 2. 高层脑始终介入输入信号化
        match_result = self.higher_brain.process(input_signals)

        # 3. 反射弧产生原始输出
        context = {
            "cortex_confidence": self.higher_brain.get_confidence(),
            "phase": self.phase,
        }
        raw_outputs = self.reflex.execute(input_signals, context)

        # 4. 高层脑介入输出处理（失败时反射弧保底）
        try:
            final_outputs = self.higher_brain.intervene(
                raw_outputs, match_result
            )
            if not final_outputs and raw_outputs:
                final_outputs = raw_outputs
        except Exception:
            final_outputs = raw_outputs

        # 5. 事件驱动主循环：用 dispatcher 分发组合信号，强化激活路径
        combined_signal = self._combine_signals(input_signals)
        events = self.higher_brain.dispatch_signal(
            combined_signal.data, source_tag=f"awake_{self.step_count}"
        )
        triggered = self.higher_brain.resolve_triggers(
            events, threshold=0.01, coincidence_window=0.1
        )
        if len(triggered) >= 2:
            path = [e.target_neuron for e in triggered]
            self._reinforce_path_via_sheaths(path, amount=0.02)

        # 6. 写出端口
        self._write_output_ports(final_outputs)

        # 7. 记录 4 元组到 _trajectory_log（反事实素材）
        # 同时调用 higher_brain.record_for_dream 供高层脑自身做梦
        self.higher_brain.record_for_dream(
            input_signals, raw_outputs, final_outputs, match_result
        )
        self._trajectory_log.append(
            (dict(input_signals), dict(raw_outputs),
             dict(final_outputs), dict(match_result))
        )
        if len(self._trajectory_log) > 1000:
            self._trajectory_log.pop(0)

        # 8. 累积新奇性（基于覆盖度）
        active_channels = set(input_signals.keys())
        self.higher_brain.engine.accumulate_novelty(
            combined_signal.data, active_channels
        )

        # 9. 可能分化（threshold 内部门控）
        diff_idx = self.higher_brain.engine.maybe_differentiate(
            combined_signal.data, active_channels
        )
        if self.step_count % 1000 == 0:
            self.higher_brain.engine.autophagy()

        # 10. 阶段切换
        if self.step_count == 10000:
            self.phase = "exploratory"
        if self.step_count == 100000:
            self.phase = "mature"
            self.reflex.disable_for_mime("text/*")

        return {
            "outputs": final_outputs,
            "match_result": match_result,
            "lambda": self.higher_brain._last_lambda,
            "differentiated": diff_idx,
            "step": self.step_count,
        }

    def step_sleep(
        self,
        external_inputs: Optional[dict[str, Signal]] = None,
    ) -> dict[str, Any]:
        """睡眠态单步运行：四相位做梦学习（增强学习机制，对外界敏感）

        睡眠态不是"切断外界纯重放"，而是以做梦学习为主、外界输入为辅的
        增强学习模式。外界输入在两个相位被利用：
        - NREM S2 重放：外界输入作为"梦境扰动"叠加到重放信号（创造性融合）
        - REM 前向预演：用**当前外界输入**（而非历史 input）触发反射弧预测

        每个 sleep cycle 依次执行四个相位（全部 sheath_registry 操作，无梯度）：
        1. NREM S3 稳态缩放：sheath_registry.homeostatic_scale(beta)
        2. NREM S2 生成重放：重放轨迹 + 外界输入扰动，dispatch_signal 分发，thicken_sheath 增厚
        3. REM 反事实：对比"高层干预 vs 反射本会输出"，learn_from_intervention_delta
        4. REM 前向预演（Preplay）：当前外界输入触发预测，路径一致性 thicken/decay_sheath

        睡眠态仍产生弱输出：反射弧对外界输入响应 + 高层脑低 λ 轻度介入
        （非完全切断，对应"梦游/梦话"的弱响应）

        返回 {sleep_outputs, phases: {homeostasis, replay, counterfactual, preplay}}
        """
        self.mode = SystemMode.SLEEP

        # 读取外界输入（默认从入端口）
        if external_inputs is None:
            external_inputs = self._read_input_ports()
        has_external = bool(external_inputs)
        has_trajectory = bool(self._trajectory_log)

        # 无历史轨迹且无外界输入：无事可做
        if not has_trajectory and not has_external:
            return {}

        results: dict[str, Any] = {}

        # 相位 1：NREM S3 稳态缩放（纯 sheath_registry 操作，与外界无关）
        if has_trajectory:
            results["homeostasis"] = self._sleep_phase_homeostasis()

        # 相位 2：NREM S2 生成重放（外界输入作为梦境扰动注入）
        if has_trajectory:
            results["replay"] = self._sleep_phase_replay(external_inputs)

        # 相位 3：REM 反事实（对比历史干预差异）
        if has_trajectory:
            results["counterfactual"] = self._sleep_phase_counterfactual()

        # 相位 4：REM 前向预演（当前外界输入触发预测，对比历史实际路径）
        if has_trajectory and has_external:
            results["preplay"] = self._sleep_phase_preplay(external_inputs)

        # 睡眠态输出：反射弧对外界输入响应 + 高层脑低 λ 轻度介入
        sleep_outputs: dict[str, Signal] = {}
        if has_external:
            context = {
                "cortex_confidence": self.higher_brain.get_confidence(),
                "phase": "sleep",
            }
            reflex_outputs = self.reflex.execute(external_inputs, context)
            if reflex_outputs:
                # 高层脑在睡眠态仍介入，但 λ 整体偏低（运动弛缓 + 弱响应）
                match = self.higher_brain.process(external_inputs)
                match["sleep_mode"] = True  # 触发低 λ 路径
                try:
                    sleep_outputs = self.higher_brain.intervene(
                        reflex_outputs, match
                    )
                    if not sleep_outputs:
                        sleep_outputs = reflex_outputs
                except Exception:
                    sleep_outputs = reflex_outputs
                self._write_output_ports(sleep_outputs)
        results["sleep_outputs"] = sleep_outputs
        return results

    def _sleep_phase_homeostasis(self) -> dict[str, Any]:
        """相位 1：NREM S3 稳态缩放

        突触稳态假说：全局髓鞘按保护系数加权衰减 gain。
        核心层（高保护）几乎不变，活跃层（低保护）优先衰减。
        相对强弱保持，绝对强度下降，清理噪声 + 重置学习容量。
        用 sheath_registry.homeostatic_scale(beta)。
        """
        sheath_reg = self.higher_brain.sheath_registry
        sheaths_before = len(sheath_reg._sheaths)
        sheath_reg.homeostatic_scale(beta=self.sleep_beta)
        sheaths_after = len(sheath_reg._sheaths)
        return {
            "phase": "homeostasis",
            "sheaths_before": sheaths_before,
            "sheaths_after": sheaths_after,
            "scaled": sheaths_before,
        }

    def _sleep_phase_replay(
        self,
        external_inputs: Optional[dict[str, Signal]] = None,
    ) -> dict[str, Any]:
        """相位 2：NREM S2 生成重放（外界输入作为梦境扰动注入）

        从轨迹日志取最近一段，用 higher_brain.dispatch_signal 分发重放信号，
        走通的路径用 sheath_registry.thicken_sheath 增厚（用进废退）。
        若存在外界输入，将其作为"梦境扰动"叠加到重放信号上——对应生物学中
        外界刺激被整合进梦境的现象（如水声→梦中瀑布），让重放不再是机械复刻，
        而是与当前感知的创造性融合。
        """
        input_signals, _, _, _ = self._trajectory_log[-1]

        # 外界输入作为梦境扰动叠加到重放信号
        replay_inputs = dict(input_signals)
        if external_inputs:
            for key, ext_sig in external_inputs.items():
                if key in replay_inputs:
                    orig = replay_inputs[key].data
                    ext = ext_sig.data
                    if orig.shape == ext.shape:
                        blended = orig + ext * 0.1
                        replay_inputs[key] = Signal(
                            data=blended,
                            mime_type=replay_inputs[key].mime_type,
                            metadata={**replay_inputs[key].metadata,
                                      "dream_disturbed": True},
                        )
                else:
                    # 新端口的外界输入直接加入梦境
                    replay_inputs[key] = ext_sig

        # 高层脑处理重放信号（激活路径 + 记录激活）
        replay_match = self.higher_brain.process(replay_inputs)

        # 事件驱动分发重放信号，强化走通的路径
        combined = self._combine_signals(replay_inputs)
        events = self.higher_brain.dispatch_signal(
            combined.data, source_tag="replay"
        )
        triggered = self.higher_brain.resolve_triggers(
            events, threshold=0.01, coincidence_window=0.1
        )
        if len(triggered) >= 2:
            path = [e.target_neuron for e in triggered]
            self._reinforce_path_via_sheaths(path, amount=0.02)

        return {
            "phase": "replay",
            "winner_id": replay_match.get("winner_id", -1),
            "disturbed_by_external": bool(external_inputs),
            "triggered_count": len(triggered),
        }

    def _sleep_phase_counterfactual(self) -> dict[str, Any]:
        """相位 3：REM 反事实

        对比"高层干预 vs 反射本会输出"的差异，调用
        higher_brain.learn_from_intervention_delta 微调权重。
        差异越大，说明高层干预越显著，权重调整幅度越大。
        """
        _, reflex_outputs, final_outputs, _ = self._trajectory_log[-1]
        # 从干预差异学习——微调被干预神经元的权重
        self.higher_brain.learn_from_intervention_delta(
            reflex_outputs, final_outputs
        )
        # 计算差异幅度
        total_delta = 0.0
        count = 0
        for key in final_outputs:
            if key in reflex_outputs:
                diff = (
                    final_outputs[key].data - reflex_outputs[key].data
                ).abs().mean().item()
                total_delta += diff
                count += 1
        avg_delta = total_delta / count if count > 0 else 0.0
        return {
            "phase": "counterfactual",
            "intervention_delta": avg_delta,
        }

    def _sleep_phase_preplay(
        self,
        external_inputs: dict[str, Signal],
    ) -> dict[str, Any]:
        """相位 4：REM 前向预演（Preplay）— 真正的 WAM-TTT 测试时训练

        用**当前外界输入**（而非历史 input_signals）触发反射弧生成预测，
        用 higher_brain.dispatch_signal 分发预测信号，按路径激活一致性
        sheath_registry.thicken_sheath 强化 / sheath_registry.decay_sheath 衰减。

        对应 WAM-TTT 的自监督预测，但用髓鞘语言实现（无梯度）：
        - 对**新输入**做预测（不是重放历史）→ 这才是"测试时训练"
        - 预测路径与历史实际路径一致 → thicken_sheath 强化（模型可迁移）
        - 预测路径与历史实际路径不一致 → decay_sheath 衰减（模型需修正）
        """
        _, _, _, match_result = self._trajectory_log[-1]
        actual_trajectory = match_result.get("trajectory", [])

        # 事件驱动分发当前外界输入，看激活哪条路径（预测路径）
        predicted_match = self.higher_brain.process(external_inputs)
        combined = self._combine_signals(external_inputs)
        events = self.higher_brain.dispatch_signal(
            combined.data, source_tag="preplay"
        )
        triggered = self.higher_brain.resolve_triggers(
            events, threshold=0.01, coincidence_window=0.1
        )
        predicted_path = [e.target_neuron for e in triggered]

        if predicted_path and actual_trajectory:
            pred_set = set(predicted_path)
            actual_set = set(actual_trajectory)
            overlap = (
                len(pred_set & actual_set) / len(actual_set)
                if actual_set else 0.0
            )

            if overlap >= self.sleep_preplay_consistency:
                # 预测与历史经验一致 → 强化历史实际路径（thicken_sheath）
                self._reinforce_path_via_sheaths(
                    actual_trajectory, amount=0.03
                )
            else:
                # 不一致 → 衰减预测路径（decay_sheath）
                self._decay_path_via_sheaths(
                    predicted_path, amount=0.02
                )

            return {
                "phase": "preplay",
                "overlap": overlap,
                "consistent": overlap >= self.sleep_preplay_consistency,
                "predicted_on": "external_input",
            }
        return {
            "phase": "preplay",
            "overlap": 0.0,
            "consistent": False,
            "predicted_on": "external_input",
        }

    def check_convergence(
        self,
        weight_delta: float,
        myelin_stable: bool,
    ) -> ConvergenceState:
        """收敛判据集成——委托 engine.check_convergence

        Args:
            weight_delta: 权重变化量（< ε 时收敛）
            myelin_stable: 髓鞘拓扑是否稳定
        """
        return self.higher_brain.engine.check_convergence(
            weight_delta=weight_delta,
            myelin_stable=myelin_stable,
        )

    # ============================================================
    # 状态持久化（只保存脑状态：权重 W + 髓鞘 + 发育元数据）
    # ============================================================

    def save_state(self, path: str) -> None:
        """保存脑状态到目录

        保存内容：
        - neurons: seed / W (Tensor) / unfolded (DimSlice) / parent_seed / alive
        - sheaths: 所有髓鞘的 delay/gain/protection + 连接信息
        - engine: novelty_accumulator / novelty_threshold / differentiation_count
        - system: phase / step_count / port_layout

        不保存：_trajectory_log（梦境素材，临时性）、ports（外部连接，运行时重建）

        格式：{path}/brain.json（元数据）+ {path}/tensors.pt（所有 Tensor）
        """
        os.makedirs(path, exist_ok=True)

        # 1. 收集神经元元数据 + Tensor
        eco = self.higher_brain.ecosystem
        neurons_meta = []
        tensors: dict[str, torch.Tensor] = {}
        for idx, neuron in eco.neurons.items():
            unfolded_meta = {
                ch: {
                    "dim_idx": slc.dim_idx,
                    "size": slc.size,
                    "gain": slc.gain,
                    "activity": slc.activity,
                    "protection": slc.protection,
                    "myelinated": slc.myelinated,
                }
                for ch, slc in neuron.unfolded.items()
            }
            neurons_meta.append({
                "idx": idx,
                "seed": neuron.seed,
                "parent_seed": neuron.parent_seed,
                "alive": neuron.alive,
                "metabolism": neuron.metabolism,
                "unfolded": unfolded_meta,
                "has_W": neuron.W is not None,
            })
            if neuron.W is not None:
                tensors[f"neuron_{idx}_W"] = neuron.W

        # 2. 收集髓鞘
        sheaths_meta = []
        reg = self.higher_brain.sheath_registry
        for key, sheath in reg._sheaths.items():
            sheaths_meta.append({
                "src_neuron": sheath.src_neuron,
                "src_channel": sheath.src_channel,
                "dst_neuron": sheath.dst_neuron,
                "dst_channel": sheath.dst_channel,
                "delay": sheath.delay,
                "gain": sheath.gain,
                "protection": sheath.protection,
            })

        # 3. 发育引擎状态
        engine = self.higher_brain.engine
        engine_meta = {
            "novelty_accumulator": engine._novelty_accumulator,
            "novelty_threshold": engine.novelty_threshold,
            "novelty_decay": engine.novelty_decay,
            "differentiation_count": engine._differentiation_count,
            "total_signal_count": engine._total_signal_count,
        }

        # 4. 系统元数据
        system_meta = {
            "phase": self.phase,
            "step_count": self.step_count,
            "port_layout": self.port_layout,
        }

        brain_json = {
            "system": system_meta,
            "neurons": neurons_meta,
            "sheaths": sheaths_meta,
            "engine": engine_meta,
        }

        with open(os.path.join(path, "brain.json"), "w", encoding="utf-8") as f:
            json.dump(brain_json, f, ensure_ascii=False, indent=2)

        if tensors:
            torch.save(tensors, os.path.join(path, "tensors.pt"))

    def load_state(self, path: str) -> None:
        """从目录加载脑状态

        恢复 save_state 保存的所有内容。
        注意：ports（外部连接）需在 load_state 后由外部重新注册。
        """
        from mcp.developmental.neuron import Neuron, DimSlice

        with open(os.path.join(path, "brain.json"), "r", encoding="utf-8") as f:
            brain_json = json.load(f)

        tensors: dict[str, torch.Tensor] = {}
        tensors_path = os.path.join(path, "tensors.pt")
        if os.path.exists(tensors_path):
            tensors = torch.load(tensors_path, weights_only=False)

        # 1. 恢复系统元数据
        sys_meta = brain_json["system"]
        # port_layout 不一致时报错（JSON 把 tuple 序列化成 list，需归一化比较）
        saved_layout = {k: tuple(v) for k, v in sys_meta["port_layout"].items()}
        if saved_layout != self.port_layout:
            raise ValueError(
                f"port_layout mismatch: saved={saved_layout} "
                f"current={self.port_layout}"
            )
        self.phase = sys_meta["phase"]
        self.step_count = sys_meta["step_count"]

        # 2. 恢复神经元生态
        eco = self.higher_brain.ecosystem
        eco.neurons.clear()
        eco._next_idx = 0

        for n_meta in brain_json["neurons"]:
            neuron = Neuron(
                seed=n_meta["seed"],
                port_layout=self.port_layout,
            )
            neuron.parent_seed = n_meta.get("parent_seed")
            neuron.alive = n_meta["alive"]
            neuron.metabolism = n_meta.get("metabolism", 0.5)

            # 恢复 unfolded + W
            for ch, slc_meta in n_meta["unfolded"].items():
                slc = DimSlice(
                    dim_idx=slc_meta["dim_idx"],
                    size=slc_meta["size"],
                    gain=slc_meta["gain"],
                    activity=slc_meta["activity"],
                    protection=slc_meta["protection"],
                    myelinated=slc_meta["myelinated"],
                )
                neuron.unfolded[ch] = slc

            if n_meta["has_W"]:
                key = f"neuron_{n_meta['idx']}_W"
                if key in tensors:
                    neuron.W = tensors[key]

            eco.neurons[n_meta["idx"]] = neuron
            if n_meta["idx"] >= eco._next_idx:
                eco._next_idx = n_meta["idx"] + 1

        # 3. 恢复髓鞘
        reg = self.higher_brain.sheath_registry
        reg._sheaths.clear()
        for s_meta in brain_json["sheaths"]:
            reg.add_sheath(
                src_neuron=s_meta["src_neuron"],
                src_channel=s_meta["src_channel"],
                dst_neuron=s_meta["dst_neuron"],
                dst_channel=s_meta["dst_channel"],
                delay=s_meta["delay"],
                gain=s_meta["gain"],
                protection=s_meta["protection"],
            )

        # 4. 恢复发育引擎
        engine = self.higher_brain.engine
        eng_meta = brain_json["engine"]
        engine._novelty_accumulator = eng_meta["novelty_accumulator"]
        engine.novelty_threshold = eng_meta["novelty_threshold"]
        engine.novelty_decay = eng_meta["novelty_decay"]
        engine._differentiation_count = eng_meta["differentiation_count"]
        engine._total_signal_count = eng_meta["total_signal_count"]
