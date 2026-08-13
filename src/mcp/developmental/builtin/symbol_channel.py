"""原子工具：符号信道信号源

LLM 输出作为符号信道信号源，与视觉/听觉信道同级。
输入：text/* 信号
输出：text/embedding 信号（张量）
对高层脑而言与 EchoFunction 无差别。
"""
import hashlib
import torch
from mcp.developmental.reptilian import ReptilianFunction
from mcp.developmental.signal import Signal


class SymbolChannelFunction(ReptilianFunction):
    """符号信道：把文本转成定长嵌入向量

    默认用确定性哈希嵌入（测试用），可替换为真实 LLM 嵌入。
    """

    def __init__(self, embed_dim: int = 512):
        self.embed_dim = embed_dim

    def get_input_spec(self):
        return {"text": "text/plain"}

    def get_output_spec(self):
        return {"symbol": "text/embedding"}

    def execute(self, inputs):
        text_sig = inputs["text"]
        if not text_sig.mime_type.startswith("text/"):
            raise ValueError(
                f"SymbolChannelFunction requires text/* input, "
                f"got {text_sig.mime_type}"
            )
        # 确定性哈希嵌入（模拟 LLM embedding）
        raw = text_sig.metadata.get("raw", str(text_sig.data.tolist()))
        h = hashlib.sha256(raw.encode()).digest()
        # 重复哈希填满 embed_dim
        while len(h) < self.embed_dim * 4:
            h += hashlib.sha256(h).digest()
        embed = torch.tensor(
            [b / 255.0 * 2 - 1 for b in h[:self.embed_dim * 4:4]],
            dtype=torch.float32,
        )
        return {
            "symbol": Signal(
                data=embed,
                mime_type="text/embedding",
                metadata={"raw": raw, "source": "symbol_channel"},
            )
        }
