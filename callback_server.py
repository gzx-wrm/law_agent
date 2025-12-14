#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号回调接口测试服务
用于模拟接收法律助手系统的回调消息
"""

import uvicorn
from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
from contextlib import asynccontextmanager
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 60)
    print("🚀 微信公众号回调接口测试服务启动")
    print(f"📡 服务地址: http://localhost:8080")
    print(f"📝 接收回调接口: /send_custom_message")
    print("=" * 60)
    yield
    print("\n🛑 微信公众号回调接口测试服务关闭")


app = FastAPI(
    title="微信回调测试服务",
    description="用于测试法律助手系统的回调功能",
    version="1.0.0",
    lifespan=lifespan
)


@app.post("/send_custom_message", response_class=PlainTextResponse)
async def send_custom_message(
    openid: str = Form(..., description="用户OpenID"),
    message_type: str = Form(..., description="消息类型"),
    content: str = Form(..., description="消息内容")
):
    """
    接收法律助手系统的回调消息
    """
    print("\n" + "🔔 收到回调消息 " + "🔔")
    print("-" * 50)
    print(f"👤 用户OpenID: {openid}")
    print(f"📨 消息类型: {message_type}")
    print(f"💬 消息内容:")
    print(f"   {content}")
    print("-" * 50)
    print(f"📏 消息长度: {len(content)} 字符")

    # 检查消息长度限制
    if len(content) > 2048:
        print(f"⚠️  警告: 消息长度超过2048字符限制")

    return "OK"


@app.get("/", response_class=PlainTextResponse)
async def root():
    """根路径，用于检查服务状态"""
    return "微信回调测试服务正在运行"


@app.get("/health", response_class=PlainTextResponse)
async def health_check():
    """健康检查接口"""
    return "OK"


def run_callback_server():
    """启动回调测试服务器"""
    print("准备启动微信回调测试服务...")
    uvicorn.run(
        app,
        host="localhost",
        port=8080,
        log_level="info"
    )


if __name__ == "__main__":
    run_callback_server()