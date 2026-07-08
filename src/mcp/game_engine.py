"""TS2 多人实时游戏引擎
Multiplayer Arena Battle — 后端物理模拟与游戏状态管理
"""

import asyncio
import json
import logging
import math
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ─── 游戏常量 ────────────────────────────────────────────────

ARENA_WIDTH = 1200
ARENA_HEIGHT = 800
PLAYER_RADIUS = 18
PROJECTILE_RADIUS = 5
PLAYER_SPEED = 4.0
PROJECTILE_SPEED = 8.0
SHOOT_COOLDOWN = 0.3  # 秒
MAX_PLAYERS = 20
MAX_PROJECTILES = 200
GAME_TICK = 1 / 60  # 60 FPS

# ─── 数据结构 ────────────────────────────────────────────────


@dataclass
class Player:
    id: str
    name: str
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    angle: float = 0.0
    color: str = "#00ff88"
    health: float = 100.0
    score: int = 0
    kills: int = 0
    deaths: int = 0
    last_shot: float = 0.0
    alive: bool = True
    respawn_timer: float = 0.0


@dataclass
class Projectile:
    id: str
    player_id: str
    x: float
    y: float
    vx: float
    vy: float
    lifetime: float = 2.0


@dataclass
class PowerUp:
    id: str
    x: float
    y: float
    type: str  # "health", "speed", "shield"
    active: bool = True
    respawn_time: float = 10.0


# ─── 游戏引擎 ────────────────────────────────────────────────


class GameEngine:
    """核心游戏引擎 — 管理所有游戏状态和物理模拟"""

    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.projectiles: List[Projectile] = []
        self.power_ups: List[PowerUp] = []
        self.clients: Dict[str, Set[str]] = {}  # ws_id -> set of player_ids
        self.running = False
        self.tick_count = 0
        self.start_time = 0.0
        self._power_up_timer = 0.0
        self._cleanup_timer = 0.0

        # 初始化道具
        self._spawn_power_ups()

    def _spawn_power_ups(self, count: int = 8):
        """在竞技场中生成道具"""
        types = ["health", "speed", "shield"]
        for _ in range(count):
            self.power_ups.append(PowerUp(
                id=str(uuid.uuid4())[:8],
                x=random.uniform(50, ARENA_WIDTH - 50),
                y=random.uniform(50, ARENA_HEIGHT - 50),
                type=random.choice(types),
            ))

    def add_player(self, name: str, ws_id: str) -> Player:
        """添加新玩家"""
        player_id = str(uuid.uuid4())[:8]
        player = Player(
            id=player_id,
            name=name,
            x=random.uniform(100, ARENA_WIDTH - 100),
            y=random.uniform(100, ARENA_HEIGHT - 100),
            color=self._random_color(),
        )
        self.players[player_id] = player
        if ws_id not in self.clients:
            self.clients[ws_id] = set()
        self.clients[ws_id].add(player_id)
        return player

    def remove_player(self, player_id: str):
        """移除玩家"""
        if player_id in self.players:
            del self.players[player_id]
        # 移除该玩家的子弹
        self.projectiles = [p for p in self.projectiles if p.player_id != player_id]

    def remove_client(self, ws_id: str):
        """移除 WebSocket 客户端及其所有玩家"""
        if ws_id in self.clients:
            for player_id in list(self.clients[ws_id]):
                self.remove_player(player_id)
            del self.clients[ws_id]

    def move_player(self, player_id: str, vx: float, vy: float, angle: float):
        """更新玩家输入"""
        player = self.players.get(player_id)
        if not player or not player.alive:
            return
        player.vx = vx
        player.vy = vy
        player.angle = angle

    def shoot(self, player_id: str) -> Optional[Projectile]:
        """玩家射击"""
        player = self.players.get(player_id)
        if not player or not player.alive:
            return None
        now = time.time()
        if now - player.last_shot < SHOOT_COOLDOWN:
            return None
        player.last_shot = now

        # 计算子弹方向
        vx = math.cos(player.angle) * PROJECTILE_SPEED
        vy = math.sin(player.angle) * PROJECTILE_SPEED

        proj = Projectile(
            id=str(uuid.uuid4())[:8],
            player_id=player_id,
            x=player.x + math.cos(player.angle) * (PLAYER_RADIUS + 5),
            y=player.y + math.sin(player.angle) * (PLAYER_RADIUS + 5),
            vx=vx,
            vy=vy,
        )
        self.projectiles.append(proj)

        # 限制最大子弹数
        if len(self.projectiles) > MAX_PROJECTILES:
            self.projectiles = self.projectiles[-MAX_PROJECTILES:]

        return proj

    def tick(self):
        """游戏主循环 — 物理模拟"""
        self.tick_count += 1
        now = time.time()
        dt = GAME_TICK

        # 更新玩家位置
        for player in self.players.values():
            if not player.alive:
                player.respawn_timer -= dt
                if player.respawn_timer <= 0:
                    player.alive = True
                    player.health = 100.0
                    player.x = random.uniform(100, ARENA_WIDTH - 100)
                    player.y = random.uniform(100, ARENA_HEIGHT - 100)
                    player.vx = 0
                    player.vy = 0
                continue

            # 移动
            speed = PLAYER_SPEED
            player.x += player.vx * speed
            player.y += player.vy * speed

            # 边界碰撞
            player.x = max(PLAYER_RADIUS, min(ARENA_WIDTH - PLAYER_RADIUS, player.x))
            player.y = max(PLAYER_RADIUS, min(ARENA_HEIGHT - PLAYER_RADIUS, player.y))

        # 更新子弹
        to_remove = []
        for proj in self.projectiles:
            proj.x += proj.vx
            proj.y += proj.vy
            proj.lifetime -= dt

            # 边界移除
            if (proj.x < -50 or proj.x > ARENA_WIDTH + 50 or
                proj.y < -50 or proj.y > ARENA_HEIGHT + 50 or
                proj.lifetime <= 0):
                to_remove.append(proj.id)
                continue

            # 碰撞检测：子弹 vs 玩家
            shooter = self.players.get(proj.player_id)
            for player in self.players.values():
                if (player.id == proj.player_id or not player.alive):
                    continue
                dx = proj.x - player.x
                dy = proj.y - player.y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist < PLAYER_RADIUS + PROJECTILE_RADIUS:
                    player.health -= 20.0
                    to_remove.append(proj.id)
                    if player.health <= 0:
                        player.alive = False
                        player.deaths += 1
                        player.respawn_timer = 3.0
                        if shooter:
                            shooter.score += 100
                            shooter.kills += 1
                    break

        self.projectiles = [p for p in self.projectiles if p.id not in to_remove]

        # 道具生成
        self._power_up_timer += dt
        if self._power_up_timer > 5.0:
            self._power_up_timer = 0
            if len(self.power_ups) < 10:
                self.power_ups.append(PowerUp(
                    id=str(uuid.uuid4())[:8],
                    x=random.uniform(50, ARENA_WIDTH - 50),
                    y=random.uniform(50, ARENA_HEIGHT - 50),
                    type=random.choice(["health", "speed", "shield"]),
                ))

        # 道具拾取
        for pu in self.power_ups:
            if not pu.active:
                continue
            for player in self.players.values():
                if not player.alive:
                    continue
                dx = pu.x - player.x
                dy = pu.y - player.y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist < PLAYER_RADIUS + 15:
                    if pu.type == "health":
                        player.health = min(100, player.health + 30)
                    elif pu.type == "speed":
                        pass  # 速度提升效果
                    pu.active = False

        # 清理非活跃道具
        self.power_ups = [p for p in self.power_ups if p.active]

    def get_state(self) -> dict:
        """获取完整游戏状态（用于广播）"""
        return {
            "tick": self.tick_count,
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "x": round(p.x, 1),
                    "y": round(p.y, 1),
                    "angle": round(p.angle, 3),
                    "color": p.color,
                    "health": round(p.health, 1),
                    "score": p.score,
                    "kills": p.kills,
                    "deaths": p.deaths,
                    "alive": p.alive,
                }
                for p in self.players.values()
            ],
            "projectiles": [
                {
                    "id": p.id,
                    "x": round(p.x, 1),
                    "y": round(p.y, 1),
                }
                for p in self.projectiles
            ],
            "powerUps": [
                {
                    "id": p.id,
                    "x": round(p.x, 1),
                    "y": round(p.y, 1),
                    "type": p.type,
                }
                for p in self.power_ups
            ],
            "arena": {
                "width": ARENA_WIDTH,
                "height": ARENA_HEIGHT,
            },
        }

    def get_leaderboard(self) -> list:
        """获取排行榜"""
        sorted_players = sorted(
            self.players.values(),
            key=lambda p: p.score,
            reverse=True,
        )
        return [
            {
                "rank": i + 1,
                "name": p.name,
                "score": p.score,
                "kills": p.kills,
                "deaths": p.deaths,
            }
            for i, p in enumerate(sorted_players[:10])
        ]

    def _random_color(self) -> str:
        """生成随机鲜艳颜色"""
        hue = random.uniform(0, 360)
        return f"hsl({hue:.0f}, 80%, 55%)"


# ─── 全局实例 ────────────────────────────────────────────────

_engine: Optional[GameEngine] = None
_game_task: Optional[asyncio.Task] = None
_ws_connections: Dict[str, asyncio.Queue] = {}  # ws_id -> message queue


def get_engine() -> GameEngine:
    global _engine
    if _engine is None:
        _engine = GameEngine()
    return _engine


async def game_loop():
    """异步游戏主循环"""
    engine = get_engine()
    engine.running = True
    engine.start_time = time.time()

    while engine.running:
        tick_start = time.time()
        engine.tick()

        # 广播游戏状态
        state = engine.get_state()
        state_json = json.dumps({
            "type": "game_state",
            "data": state,
        })

        # 发送到所有连接的客户端
        dead_ws = []
        for ws_id, queue in _ws_connections.items():
            try:
                queue.put_nowait(state_json)
            except asyncio.QueueFull:
                pass
            except Exception:
                dead_ws.append(ws_id)

        for ws_id in dead_ws:
            if ws_id in _ws_connections:
                del _ws_connections[ws_id]

        # 维持 60 FPS
        elapsed = time.time() - tick_start
        sleep_time = GAME_TICK - elapsed
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)


def start_game_loop():
    """启动游戏循环（在事件循环中运行）"""
    global _game_task
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            _game_task = asyncio.ensure_future(game_loop())
    except RuntimeError:
        pass

def stop_game_loop():
    """停止游戏循环"""
    global _game_task, _engine
    if _engine:
        _engine.running = False
    if _game_task and not _game_task.done():
        _game_task.cancel()
        _game_task = None
    logger.info("Game engine stopped")
