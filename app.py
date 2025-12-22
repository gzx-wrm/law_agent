import asyncio
import json
import sys
import time
import uuid
from contextlib import asynccontextmanager

import aiosqlite
import requests
from aiosqlite import Connection
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import PlainTextResponse
from langchain.agents import initialize_agent, AgentType
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import httpx

from chain.chain import get_law_qa_chain
from embedding.embedding import AliEmbeddings
from flow.flow import get_law_qa_flow
from model.model import get_model_ali, get_langgraph_model
from retriever.retriever import get_es_retriever, get_multi_query_retriever
from tool.tool import get_law_documents_retriever_tool
from config.config_manager import SystemConfig, init_config_manager


graph = None
default_user_id = "1"
asqlite_conn: Connection = None
# 存储request_id到超时回调的映射
pending_requests = {}
admin_db_conn = None


def generate_request_id():
    """生成全局唯一的request_id"""
    return str(uuid.uuid4())


async def init_admin_db():
    """初始化管理数据库连接"""
    global admin_db_conn
    if admin_db_conn is None:
        admin_db_conn = await aiosqlite.connect("admin_management.sqlite")
    return admin_db_conn


def init_law_agent():
    model = get_model_ali()
    embedding = AliEmbeddings()
    law_retriever = get_es_retriever("law_documents", embedding)
    retriever_tool = get_law_documents_retriever_tool(law_retriever)

    law_agent = initialize_agent(
        tools=[retriever_tool],
        llm=model,
        agent=AgentType.CHAT_ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        handle_parsing_errors=True,
    )
    chain = get_law_qa_chain(law_agent, model)
    return chain

async def init_law_flow(with_memory=False, use_multi_query_retriever=True):
    global graph, asqlite_conn
    llm = get_langgraph_model()
    embedding = AliEmbeddings()
    law_index_name = SystemConfig.get_law_index_name()
    law_retriever = get_es_retriever(law_index_name, embedding)
    if use_multi_query_retriever:
        law_retriever = get_multi_query_retriever(law_retriever, llm)

    retriever_tool = get_law_documents_retriever_tool(law_retriever)

    # 检查点和存储器
    checkpoints_db_name = SystemConfig.get_checkpoints_db_name()
    asqlite_conn = await aiosqlite.connect(checkpoints_db_name, check_same_thread=False)
    checkpoint_saver = AsyncSqliteSaver(asqlite_conn)
    await checkpoint_saver.setup()
    # store = AsyncSqliteStore.from_conn_string("async_store.sqlite")
    # store = await store.__aenter__()
    graph = get_law_qa_flow(llm, embedding, law_retriever, [retriever_tool], checkpoint_saver, None)

    # print("checkpoint:", await checkpoint_saver.aget({"configurable": {"thread_id": "1"}}))
    return graph


async def chat(message, history):
    # chain = init_law_agent()
    # out_callback = OutCallbackHandler()
    # task = asyncio.create_task(
    #     chain.ainvoke({"question": message}, config={"callbacks": [out_callback]}))

    global graph
    config = {"configurable": {"thread_id": default_user_id}}
    full_response = ""
    content = ""
    async for chunk in graph.astream(
            {"messages": [{"role": "user",
                           # "content": "我骑车正常行驶在正确的非机动车道上，在通过一个路口时慢行并左右观察确认无异常时通过了，但是此时从对面突然冲出来一个小孩，我无法立即刹车因此将他撞倒，我需要承担责任吗？"}]},
                           "content": message}]},
            config=config,
            stream_mode=["messages", "custom"],
            subgraphs=True):
        if chunk[1] == "messages":
            continue
        chunk = chunk[2]["llm_chunk"]
        if chunk[0] != "messages":
            continue
        # 工具节点的输出不打印
        metadata = chunk[1][1]
        if metadata["langgraph_node"] == "tools":
            continue
        ai_message = chunk[1][0]
        if ai_message.content == "":
            continue
        full_response = full_response + ai_message.content
        yield full_response
        # print(chunk.content, end="")

async def run_shell() -> None:
    await init_law_flow()
    global graph

    while True:
        question = input("\n用户:")
        if question.strip() == "stop":
            break
        print("\n法律小助手:", end="")

        config = {"configurable": {"thread_id": "1"}}
        full_response = ""
        content = ""
        async for chunk in graph.astream(
                {"messages": [{"role": "user",
                               # "content": "我骑车正常行驶在正确的非机动车道上，在通过一个路口时慢行并左右观察确认无异常时通过了，但是此时从对面突然冲出来一个小孩，我无法立即刹车因此将他撞倒，我需要承担责任吗？"}]},
                               "content": question}]},
                config=config,
                stream_mode=["messages", "custom"],
                subgraphs=True):
            # pass
            # print("received: ", chunk)
            if chunk[1] == "messages":
                continue
            chunk = chunk[2]["llm_chunk"]
            if chunk[0] != "messages":
                continue
            # 工具节点的输出不打印
            metadata = chunk[1][1]
            if metadata["langgraph_node"] == "tools":
                continue
            ai_message = chunk[1][0]
            if ai_message.content == "":
                continue
            print(ai_message.content, end="")
        print()


async def send_callback_message(openid: str, content: str):
    """发送回调消息到微信公众号后端"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            data = {
                "openid": openid,
                "message_type": "text",
                "content": content
            }
            callback_url = SystemConfig.get_callback_url()
            print(f"callback_url: {callback_url}")
            response = await client.post(callback_url, data=data)
            print(f"Callback response code: {response.status_code}, response content: {response.text}")
    except Exception as e:
        print(f"Failed to send callback message: {e}")

def send_custom_message(openid: str, content: str):
    """通过服务器接口发送客服消息"""
    url = SystemConfig.get_callback_url()
    data = {
        "openid": openid,
        "message_type": "text",
        "content": content
    }
    try:
        resp = requests.post(
            url,
            data=json.dumps(data, ensure_ascii=False).encode('utf-8'),
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        return resp.json()
    except Exception as e:
        print(f"发送客服消息失败: {e}")
        return {"errcode": -1, "errmsg": str(e)}

async def is_request_already_processed(request_id: str) -> bool:
    """检查request_id是否已经被处理过"""
    if not request_id:
        return False

    global admin_db_conn
    if not admin_db_conn:
        return False

    try:
        cursor = await admin_db_conn.execute(
            "SELECT request_id FROM query_logs WHERE request_id = ?",
            (request_id,)
        )
        existing_record = await cursor.fetchone()
        return existing_record is not None
    except Exception as e:
        print(f"Error checking request ID: {e}")
        return False


async def log_query_data(user_id: str, question: str, response: str, response_time: float, status: str = "success", request_id: str = None):
    """记录请求据到后台管理数据库"""
    global admin_db_conn
    if not admin_db_conn:
        return False  # 返回False表示记录失败

    try:
        # 检查是否启用数据分析
        analytics_enabled = SystemConfig.is_analytics_enabled()
        if not analytics_enabled:
            return False

        # 如果提供了request_id，检查是否已存在
        if request_id:
            if await is_request_already_processed(request_id):
                print(f"Request ID {request_id} already exists, skipping duplicate record")
                return False  # 记录已存在，跳过

        from datetime import datetime
        current_time = datetime.now()

        # 记录查询日志
        await admin_db_conn.execute(
            """INSERT INTO query_logs (user_id, question, response, response_time, status, timestamp, request_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, question, response, response_time, status, current_time, request_id)
        )

        # 更新用户统计
        await admin_db_conn.execute(
            """INSERT INTO user_stats (user_id, total_queries, last_query_time, first_query_time, total_response_time, created_at, updated_at)
               VALUES (?, 1, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
               total_queries = total_queries + 1,
               last_query_time = excluded.last_query_time,
               total_response_time = total_response_time + excluded.total_response_time,
               updated_at = excluded.updated_at""",
            (user_id, current_time, current_time, response_time, current_time, current_time)
        )

        # 更新热门问题统计
        await admin_db_conn.execute(
            """INSERT INTO popular_questions (question, count, last_asked)
               VALUES (?, 1, ?)
               ON CONFLICT(question) DO UPDATE SET
               count = count + 1,
               last_asked = excluded.last_asked""",
            (question, current_time)
        )

        await admin_db_conn.commit()
        return True  # 记录成功

    except Exception as e:
        print(f"Failed to log query data: {e}")
        return False


async def get_ai_response_with_timeout(
    message: str,
    user_id: str,
    timeout: int = None,
    request_id: str = None,
    spawn_background_on_timeout: bool = True,
) -> str:
    """获取AI响应，带超时控制"""
    global graph

    # 获取动态配置
    if timeout is None:
        timeout = SystemConfig.get_api_timeout()

    # 如果没有提供request_id，生成一个
    if not request_id:
        request_id = generate_request_id()

    config = {"configurable": {"thread_id": user_id}}
    full_response = ""
    start_time = time.time()

    try:
        # 使用asyncio.wait_for实现超时控制
        async def collect_response():
            nonlocal full_response
            async for chunk in graph.astream(
                {"messages": [{"role": "user", "content": message}]},
                config=config,
                stream_mode=["messages", "custom"],
                subgraphs=True
            ):
                if chunk[1] == "messages":
                    continue
                chunk_data = chunk[2]["llm_chunk"]
                if chunk_data[0] != "messages":
                    continue
                # 工具节点的输出不打印
                metadata = chunk_data[1][1]
                if metadata["langgraph_node"] == "tools":
                    continue
                ai_message = chunk_data[1][0]
                if ai_message.content == "":
                    continue
                full_response += ai_message.content

        if timeout and timeout > 0:
            await asyncio.wait_for(collect_response(), timeout=timeout)
        else:
            await collect_response()

        # 记录成功的查询数据
        response_time = time.time() - start_time
        log_success = await log_query_data(user_id, message, full_response, response_time, "success", request_id)

        # 如果记录成功，从pending_requests中移除
        if log_success and request_id in pending_requests:
            del pending_requests[request_id]

        return full_response

    except asyncio.TimeoutError:
        # 将请求信息存储到pending_requests中，用于后续回调
        pending_requests[request_id] = {
            "user_id": user_id,
            "message": message,
            "start_time": start_time
        }

        # 超时后继续在后台获取完整结果并发送回调
        if spawn_background_on_timeout:
            asyncio.create_task(get_and_send_callback(message, user_id, request_id))
        return "问题较复杂，正在为您查询相关法律条文，请稍后回复完整答案..."
    except Exception as e:
        # 记录失败的查询数据
        response_time = time.time() - start_time
        await log_query_data(user_id, message, str(e), response_time, "error", request_id)

        print(f"Error in get_ai_response_with_timeout: {e}")
        return "抱歉，系统暂时无法处理您的请求，请稍后再试"


async def get_and_send_callback(message: str, user_id: str, request_id: str = None):
    """后台获取完整AI响应并发送回调"""
    try:
        # 检查request_id是否已经被处理过
        if request_id and await is_request_already_processed(request_id):
            print(f"Request ID {request_id} already processed, skipping callback")
            # 从pending_requests中移除已完成的请求
            if request_id in pending_requests:
                del pending_requests[request_id]
            return

        response = await get_ai_response_with_timeout(
            message,
            user_id,
            timeout=0,
            request_id=request_id,
            spawn_background_on_timeout=False,
        )
        # 限制回调消息长度为2048字符
        if len(response) > 500:
            response = response[:500] + "..."
        # await send_callback_message(user_id, response)
        resp = send_custom_message(user_id, response)
        print(f"callback resp: {resp}")

        # 从pending_requests中移除已完成的请求
        if request_id and request_id in pending_requests:
            del pending_requests[request_id]

    except Exception as e:
        print(f"Background processing failed: {e}")
        try:
            await send_callback_message(user_id, "抱歉，系统暂时无法处理您的请求，请稍后再试")
        except Exception as callback_error:
            print(f"Failed to send error callback message: {callback_error}")
        # 即使失败也要清理pending_requests
        if request_id and request_id in pending_requests:
            del pending_requests[request_id]


@asynccontextmanager
async def lifespan(app: FastAPI):
    from config.config_manager import config_manager
    # 启动时执行
    await init_law_flow()
    await init_admin_db()  # 初始化管理数据库
    init_config_manager()  # 初始化配置管理器（同步）
    yield
    # 关闭时执行
    global asqlite_conn, admin_db_conn
    if asqlite_conn:
        await asqlite_conn.close()
    if admin_db_conn:
        await admin_db_conn.close()
    # 关闭配置管理器
    config_manager.close()


app = FastAPI(lifespan=lifespan)


@app.post("/api/chat", response_class=PlainTextResponse)
async def api_chat(
    from_user: str = Form(..., description="微信OpenID"),
    content: str = Form(..., description="消息内容"),
    type: str = Form(..., description="消息类型，固定为'text'")
):
    """微信公众号API接口"""
    global graph

    # 验证消息类型
    if type != "text":
        raise HTTPException(status_code=400, detail="只支持文本消息")

    # 验证消息内容不为空
    if not content.strip():
        return "请输入您的法律问题"

    print(f"received request: {json.dumps({'from_user': from_user, 'content': content, type: type})}")
    try:
        request_id = generate_request_id()

        pending_requests[request_id] = {
            "user_id": from_user,
            "message": content,
            "start_time": time.time()
        }

        asyncio.create_task(get_and_send_callback(content, from_user, request_id=request_id))
        return "已收到您的问题，我正在为您查询相关法律条文并整理答复，请稍等片刻。"

    except Exception as e:
        print(f"API chat error: {e}")
        return "抱歉，系统暂时无法处理您的请求，请稍后再试"


async def run_web() -> None:
    import gradio as gr
    await init_law_flow()
    demo = gr.ChatInterface(
        fn=chat, type="messages", examples=["故意杀了一个人，会判几年？", "杀人自首会减刑吗？"], title="法律AI小助手")

    demo.queue()
    demo.launch(
        server_name=SystemConfig.get_web_host(), server_port=SystemConfig.get_web_port(),
        auth=(SystemConfig.get_web_username(), SystemConfig.get_web_password()),
        auth_message="默认用户名密码: username / password")

def run_api() -> None:
    import uvicorn
    api_host = SystemConfig.get_api_host()
    api_port = SystemConfig.get_api_port()
    uvicorn.run(app, host=api_host, port=api_port)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description="please specify only one operate method once time.")
    # parser.add_argument(
    #     "-i",
    #     "--init",
    #     action="store_true",
    #     help=('''
    #             init vectorstore
    #         ''')
    # )
    parser.add_argument(
        "-s",
        "--shell",
        action="store_true",
        help=('''
                run shell
            ''')
    )
    parser.add_argument(
        "-w",
        "--web",
        action="store_true",
        help=('''
                run web
            ''')
    )
    parser.add_argument(
        "-a",
        "--api",
        action="store_true",
        help=('''
                run api server for wechat
            ''')
    )

    if len(sys.argv) <= 1:
        parser.print_help()
        exit()

    args = parser.parse_args()
    if args.shell:
        asyncio.run(run_shell())
    if args.web:
        asyncio.run(run_web())
    if args.api:
        run_api()
