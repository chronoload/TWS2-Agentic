"""patch 能力插件：自演化补丁（审计缺陷 → 固化补丁脚本 → 应用 → 重审计验证）。
修复插件（PatchPlugin 子类）继承统一抽象接口，被 Registry.discover 扫描捕捉，
与 audit.strategy 等能力在工厂中平级。"""
from .model import PatchScript, load_patch
from .generators import GENERATORS, build_patch
from .gen import gen_patches, load_issues
from .apply import apply_patch, apply_patches
from .verify import verify_patches, count_issues


def register(registry) -> None:
    """装配 patch.generator 命名空间（扫描捕捉 PatchPlugin 子类）。"""
    registry.discover("patch.generator")
