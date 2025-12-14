#!/usr/bin/env python3
"""
后台管理系统启动脚本
"""

import sys
import os
import argparse
import asyncio
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from admin_server import run_admin_server


def main():
    parser = argparse.ArgumentParser(
        description="法律AI助手后台管理系统启动脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python run_admin.py                    # 启动后台管理服务器
  python run_admin.py --host 127.0.0.1   # 指定主机地址
  python run_admin.py --port 8082        # 指定端口号
        """
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="服务器主机地址 (默认: 127.0.0.1)"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8081,
        help="服务器端口号 (默认: 8081)"
    )

    parser.add_argument(
        "--reload",
        action="store_true",
        help="启用开发模式热重载"
    )

    args = parser.parse_args()

    # 修改admin_server.py中的默认配置
    import admin_server
    admin_server.admin_app.state.host = args.host
    admin_server.admin_app.state.port = args.port

    print("="*60)
    print("🏛️  法律AI助手 - 后台管理系统")
    print("="*60)
    print(f"📍 服务地址: http://{args.host}:{args.port}")
    print(f"📚 API文档: http://{args.host}:{args.port}/docs")
    print(f"🔧 管理界面: http://{args.host}:{args.port}/admin (待开发)")
    print(f"🔑 默认管理员Token: admin123")
    print("="*60)
    print("⚠️  生产环境中请修改默认的管理员token！")
    print("="*60)

    if args.reload:
        print("🔄 开发模式已启用，支持热重载")
        import uvicorn
        uvicorn.run(
            admin_server.admin_app,
            host=args.host,
            port=args.port,
            reload=True,
            log_level="info"
        )
    else:
        try:
            import uvicorn
            uvicorn.run(
                admin_server.admin_app,
                host=args.host,
                port=args.port,
                log_level="info"
            )
        except KeyboardInterrupt:
            print("\n👋 后台管理系统已停止")
        except Exception as e:
            print(f"❌ 启动失败: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()