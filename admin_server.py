"""
后台管理系统API服务器
提供用户管理、数据分析等管理功能
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from contextlib import asynccontextmanager

from config.config_manager import DEFAULT_CONFIGS, CONFIG_DESCRIPTIONS
from config.config_manager import SystemConfig

import aiosqlite
import httpx
from fastapi import FastAPI, HTTPException, Query, Depends, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# 全局变量
admin_db_conn: Optional[aiosqlite.Connection] = None
security = HTTPBearer()


# 数据模型定义
class UserStats(BaseModel):
    user_id: str
    total_queries: int
    last_query_time: Optional[datetime] = None
    first_query_time: Optional[datetime] = None
    avg_response_time: Optional[float] = None


class SystemStats(BaseModel):
    total_users: int
    total_queries: int
    daily_queries: int
    avg_response_time: float
    system_uptime: str
    top_questions: List[Dict[str, Any]]


class UserActivity(BaseModel):
    date: str
    active_users: int
    total_queries: int
    avg_response_time: float


class ConfigUpdate(BaseModel):
    key: str = Field(..., description="配置键")
    value: str = Field(..., description="配置值")


class AdminLog(BaseModel):
    """管理员日志记录"""
    id: int
    timestamp: datetime
    level: str
    operation: str
    user_id: Optional[str] = None
    details: Optional[str] = None


# 数据库操作函数
async def init_admin_database():
    """初始化管理数据库"""
    global admin_db_conn
    admin_db_conn = await aiosqlite.connect("admin_management.sqlite", check_same_thread=False)

    # 创建用户统计表
    await admin_db_conn.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id TEXT PRIMARY KEY,
            total_queries INTEGER DEFAULT 0,
            last_query_time DATETIME,
            first_query_time DATETIME,
            total_response_time REAL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 创建查询日志表
    await admin_db_conn.execute("""
        CREATE TABLE IF NOT EXISTS query_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            question TEXT NOT NULL,
            response TEXT,
            response_time REAL,
            status TEXT DEFAULT 'success',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 创建系统配置表
    await admin_db_conn.execute("""
        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            description TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 创建管理日志表
    await admin_db_conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            level TEXT DEFAULT 'info',
            operation TEXT NOT NULL,
            user_id TEXT,
            details TEXT
        )
    """)

    # 创建热门问题表
    await admin_db_conn.execute("""
        CREATE TABLE IF NOT EXISTS popular_questions (
            question TEXT PRIMARY KEY,
            count INTEGER DEFAULT 1,
            last_asked DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await admin_db_conn.commit()
    await create_default_config()


async def create_default_config():
    """创建默认配置（合并所有配置项）"""
    # 导入配置管理器中的默认配置
    for key, value in DEFAULT_CONFIGS.items():
        await admin_db_conn.execute(
            "INSERT OR IGNORE INTO system_config (key, value, description) VALUES (?, ?, ?)",
            (key, str(value), CONFIG_DESCRIPTIONS.get(key, "未描述的配置项"))
        )

    await admin_db_conn.commit()


def get_config_description(key: str) -> str:
    """获取配置项的描述"""
    return CONFIG_DESCRIPTIONS.get(key, "未描述的配置项")


async def log_admin_operation(level: str, operation: str, user_id: str = None, details: str = None):
    """记录管理员操作日志"""
    if admin_db_conn:
        await admin_db_conn.execute(
            "INSERT INTO admin_logs (level, operation, user_id, details) VALUES (?, ?, ?, ?)",
            (level, operation, user_id, details)
        )
        await admin_db_conn.commit()


async def update_user_stats(user_id: str, response_time: float = None):
    """更新用户统计信息"""
    if not admin_db_conn:
        return

    current_time = datetime.now()

    # 检查用户是否存在
    cursor = await admin_db_conn.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,))
    user_exists = await cursor.fetchone()

    if user_exists:
        # 更新现有用户
        update_fields = ["total_queries = total_queries + 1", "last_query_time = ?", "updated_at = ?"]
        params = [current_time, current_time, user_id]

        if response_time:
            update_fields.append("total_response_time = total_response_time + ?")
            params.insert(-1, response_time)

        await admin_db_conn.execute(
            f"UPDATE user_stats SET {', '.join(update_fields)} WHERE user_id = ?",
            params
        )
    else:
        # 创建新用户
        await admin_db_conn.execute(
            """INSERT INTO user_stats
               (user_id, total_queries, last_query_time, first_query_time, total_response_time)
               VALUES (?, 1, ?, ?, ?)""",
            (user_id, current_time, current_time, response_time or 0)
        )

    await admin_db_conn.commit()


async def log_query(user_id: str, question: str, response: str, response_time: float, status: str = "success"):
    """记录查询日志"""
    if not admin_db_conn:
        return

    await admin_db_conn.execute(
        """INSERT INTO query_logs (user_id, question, response, response_time, status)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, question, response, response_time, status)
    )

    # 更新热门问题统计
    await admin_db_conn.execute(
        """INSERT INTO popular_questions (question, count, last_asked)
           VALUES (?, 1, ?)
           ON CONFLICT(question) DO UPDATE SET
           count = count + 1,
           last_asked = ?""",
        (question, datetime.now(), datetime.now())
    )

    await admin_db_conn.commit()


# 认证依赖
async def verify_admin_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """验证管理员token"""
    token = credentials.credentials

    if not admin_db_conn:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available"
        )

    cursor = await admin_db_conn.execute("SELECT value FROM system_config WHERE key = ?", ("admin_token",))
    result = await cursor.fetchone()

    if not result or result[0] != token:
        await log_admin_operation("warning", "invalid_token_attempt", None, f"Token: {token[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token"
        )

    return token


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    await init_admin_database()
    await log_admin_operation("info", "system_startup", None, "Admin management system started")
    yield
    # 关闭时执行
    global admin_db_conn
    if admin_db_conn:
        await admin_db_conn.close()


# 创建FastAPI应用
admin_app = FastAPI(
    title="法律AI助手 - 后台管理系统",
    description="提供用户管理、数据分析等管理功能",
    version="1.0.0",
    lifespan=lifespan
)

# 添加CORS中间件
admin_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API路由
@admin_app.get("/")
async def root():
    return {"message": "法律AI助手后台管理系统", "version": "1.0.0"}


@admin_app.get("/admin")
async def admin_dashboard():
    """后台管理页面"""
    try:
        with open("admin_dashboard.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return {"error": "管理页面文件未找到"}


# 用户管理接口
@admin_app.get("/api/admin/users", response_model=List[UserStats])
async def get_users(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(50, ge=1, le=1000, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索用户ID"),
    token: str = Depends(verify_admin_token)
):
    """获取用户列表和统计信息"""
    try:
        offset = (page - 1) * limit

        if search:
            cursor = await admin_db_conn.execute(
                """SELECT user_id, total_queries, last_query_time, first_query_time,
                          total_response_time / total_queries as avg_response_time
                   FROM user_stats
                   WHERE user_id LIKE ?
                   ORDER BY last_query_time DESC
                   LIMIT ? OFFSET ?""",
                (f"%{search}%", limit, offset)
            )
        else:
            cursor = await admin_db_conn.execute(
                """SELECT user_id, total_queries, last_query_time, first_query_time,
                          CASE WHEN total_queries > 0 THEN total_response_time / total_queries ELSE 0 END as avg_response_time
                   FROM user_stats
                   ORDER BY last_query_time DESC
                   LIMIT ? OFFSET ?""",
                (limit, offset)
            )

        rows = await cursor.fetchall()
        users = []

        for row in rows:
            users.append(UserStats(
                user_id=row[0],
                total_queries=row[1],
                last_query_time=datetime.fromisoformat(row[2]) if row[2] else None,
                first_query_time=datetime.fromisoformat(row[3]) if row[3] else None,
                avg_response_time=row[4]
            ))

        await log_admin_operation("info", "get_users", None, f"Page: {page}, Limit: {limit}")
        return users

    except Exception as e:
        await log_admin_operation("error", "get_users_failed", None, str(e))
        raise HTTPException(status_code=500, detail=str(e))


@admin_app.get("/api/admin/users/{user_id}/history")
async def get_user_history(
    user_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    token: str = Depends(verify_admin_token)
):
    """获取用户查询历史"""
    try:
        offset = (page - 1) * limit

        cursor = await admin_db_conn.execute(
            """SELECT question, response, response_time, status, timestamp
               FROM query_logs
               WHERE user_id = ?
               ORDER BY timestamp DESC
               LIMIT ? OFFSET ?""",
            (user_id, limit, offset)
        )

        rows = await cursor.fetchall()

        history = []
        for row in rows:
            history.append({
                "question": row[0],
                "response": row[1][:200] + "..." if row[1] and len(row[1]) > 200 else row[1],
                "response_time": row[2],
                "status": row[3],
                "timestamp": row[4]
            })

        # 获取总数
        cursor = await admin_db_conn.execute(
            "SELECT COUNT(*) FROM query_logs WHERE user_id = ?", (user_id,)
        )
        total = await cursor.fetchone()

        await log_admin_operation("info", "get_user_history", user_id, f"Page: {page}")
        return {
            "history": history,
            "total": total[0],
            "page": page,
            "limit": limit
        }

    except Exception as e:
        await log_admin_operation("error", "get_user_history_failed", user_id, str(e))
        raise HTTPException(status_code=500, detail=str(e))


# 数据分析接口
@admin_app.get("/api/admin/stats/system", response_model=SystemStats)
async def get_system_stats(token: str = Depends(verify_admin_token)):
    """获取系统统计数据"""
    try:
        # 总用户数
        cursor = await admin_db_conn.execute("SELECT COUNT(*) FROM user_stats")
        total_users = (await cursor.fetchone())[0]

        # 总请求数
        cursor = await admin_db_conn.execute("SELECT SUM(total_queries) FROM user_stats")
        total_requests_result = await cursor.fetchone()
        total_requests = total_requests_result[0] or 0

        # 今日请求数
        today = datetime.now().date()
        cursor = await admin_db_conn.execute(
            "SELECT COUNT(*) FROM query_logs WHERE DATE(timestamp) = ?",
            (today.isoformat(),)
        )
        daily_requests = (await cursor.fetchone())[0]

        # 平均响应时间
        cursor = await admin_db_conn.execute(
            "SELECT AVG(response_time) FROM query_logs WHERE response_time IS NOT NULL"
        )
        avg_response_time_result = await cursor.fetchone()
        avg_response_time = avg_response_time_result[0] or 0

        # 热门问题
        cursor = await admin_db_conn.execute(
            "SELECT question, count, last_asked FROM popular_questions ORDER BY count DESC LIMIT 10"
        )
        top_questions_rows = await cursor.fetchall()
        top_questions = [
            {"question": row[0], "count": row[1], "last_asked": row[2]}
            for row in top_questions_rows
        ]

        # 系统运行时间（这里简单返回一个示例值）
        system_uptime = "N/A"

        stats = SystemStats(
            total_users=total_users,
            total_queries=total_requests,  # 保持字段名兼容性
            daily_queries=daily_requests,
            avg_response_time=round(avg_response_time, 2),
            system_uptime=system_uptime,
            top_questions=top_questions
        )

        await log_admin_operation("info", "get_system_stats", None, "System stats retrieved")
        return stats

    except Exception as e:
        await log_admin_operation("error", "get_system_stats_failed", None, str(e))
        raise HTTPException(status_code=500, detail=str(e))


@admin_app.get("/api/admin/stats/activity")
async def get_activity_stats(
    days: int = Query(7, ge=1, le=365, description="统计天数"),
    token: str = Depends(verify_admin_token)
):
    """获取用户活动统计数据"""
    try:
        activities = []

        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).date()

            # 活跃用户数
            cursor = await admin_db_conn.execute(
                """SELECT COUNT(DISTINCT user_id) FROM query_logs
                   WHERE DATE(timestamp) = ?""",
                (date.isoformat(),)
            )
            active_users = (await cursor.fetchone())[0]

            # 总查询数
            cursor = await admin_db_conn.execute(
                "SELECT COUNT(*) FROM query_logs WHERE DATE(timestamp) = ?",
                (date.isoformat(),)
            )
            total_queries = (await cursor.fetchone())[0]

            # 平均响应时间
            cursor = await admin_db_conn.execute(
                """SELECT AVG(response_time) FROM query_logs
                   WHERE DATE(timestamp) = ? AND response_time IS NOT NULL""",
                (date.isoformat(),)
            )
            avg_response_time_result = await cursor.fetchone()
            avg_response_time = avg_response_time_result[0] or 0

            activities.append(UserActivity(
                date=date.isoformat(),
                active_users=active_users,
                total_queries=total_queries,
                avg_response_time=round(avg_response_time, 2)
            ))

        await log_admin_operation("info", "get_activity_stats", None, f"Days: {days}")
        return {"activities": list(reversed(activities))}

    except Exception as e:
        await log_admin_operation("error", "get_activity_stats_failed", None, str(e))
        raise HTTPException(status_code=500, detail=str(e))


# 系统管理接口
@admin_app.get("/api/admin/config")
async def get_system_config(token: str = Depends(verify_admin_token)):
    """获取系统配置"""
    try:
        cursor = await admin_db_conn.execute("SELECT key, value, description FROM system_config")
        rows = await cursor.fetchall()

        config_data = {}
        for row in rows:
            config_data[row[0]] = {
                "value": row[1],
                "description": row[2]
            }

        await log_admin_operation("info", "get_config", None, "System config retrieved")
        return config_data

    except Exception as e:
        await log_admin_operation("error", "get_config_failed", None, str(e))
        raise HTTPException(status_code=500, detail=str(e))


@admin_app.post("/api/admin/config")
async def update_system_config(
    config_update: ConfigUpdate,
    token: str = Depends(verify_admin_token)
):
    """更新系统配置"""
    try:
        await admin_db_conn.execute(
            """UPDATE system_config
               SET value = ?, updated_at = ?
               WHERE key = ?""",
            (config_update.value, datetime.now(), config_update.key)
        )
        await admin_db_conn.commit()

        await log_admin_operation("warning", "update_config", None,
                                f"Updated {config_update.key} to {config_update.value}")
        return {"message": "配置更新成功"}

    except Exception as e:
        await log_admin_operation("error", "update_config_failed", None, str(e))
        raise HTTPException(status_code=500, detail=str(e))


@admin_app.get("/api/admin/logs")
async def get_admin_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    level: Optional[str] = Query(None, description="日志级别"),
    token: str = Depends(verify_admin_token)
):
    """获取管理员操作日志"""
    try:
        offset = (page - 1) * limit

        if level:
            cursor = await admin_db_conn.execute(
                """SELECT id, timestamp, level, operation, user_id, details
                   FROM admin_logs
                   WHERE level = ?
                   ORDER BY timestamp DESC
                   LIMIT ? OFFSET ?""",
                (level, limit, offset)
            )
        else:
            cursor = await admin_db_conn.execute(
                """SELECT id, timestamp, level, operation, user_id, details
                   FROM admin_logs
                   ORDER BY timestamp DESC
                   LIMIT ? OFFSET ?""",
                (limit, offset)
            )

        rows = await cursor.fetchall()

        logs = []
        for row in rows:
            logs.append(AdminLog(
                id=row[0],
                timestamp=datetime.fromisoformat(row[1]),
                level=row[2],
                operation=row[3],
                user_id=row[4],
                details=row[5]
            ))

        await log_admin_operation("info", "get_logs", None, f"Page: {page}, Level: {level}")
        return {"logs": logs}

    except Exception as e:
        await log_admin_operation("error", "get_logs_failed", None, str(e))
        raise HTTPException(status_code=500, detail=str(e))


# 工具接口
@admin_app.post("/api/admin/test-webhook")
async def test_webhook(token: str = Depends(verify_admin_token)):
    """测试webhook连接"""
    try:
        # 获取回调URL配置
        callback_url = SystemConfig.get_callback_url()

        async with httpx.AsyncClient(timeout=10) as client:
            test_data = {
                "openid": "test_user",
                "message_type": "text",
                "content": "这是一条测试消息"
            }
            response = await client.post(callback_url, data=test_data)

        await log_admin_operation("info", "test_webhook", None,
                                f"Status: {response.status_code}")

        return {
            "status": "success",
            "callback_url": callback_url,
            "response_status": response.status_code,
            "response_text": response.text
        }

    except Exception as e:
        await log_admin_operation("error", "test_webhook_failed", None, str(e))
        return {
            "status": "error",
            "callback_url": callback_url if 'callback_url' in locals() else "N/A",
            "error": str(e)
        }


def run_admin_server():
    """启动后台管理服务器"""
    import uvicorn

    print("="*50)
    print("法律AI助手 - 后台管理系统")
    print("="*50)
    print(f"服务地址: http://localhost:8081")
    print(f"API文档: http://localhost:8081/docs")
    print(f"默认管理员Token: admin123")
    print("="*50)

    uvicorn.run(
        admin_app,
        host="0.0.0.0",
        port=8081,
        log_level="info"
    )


if __name__ == "__main__":
    run_admin_server()