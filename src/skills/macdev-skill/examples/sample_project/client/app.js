// 示例前端客户端 — 故意多传 payload 键（drift: extra_payload_key）
class TS2Client {
  async fetchA() { return this.api('/api/a'); }
  async createB(data) {
    // 前端传了 name，但后端端点 b 无请求模型/字段校验 → drift 候选
    return this.api('/api/b', {name: data.name});
  }
}
