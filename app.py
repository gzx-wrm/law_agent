import asyncio
import json
import re
import sys

from langchain.agents import initialize_agent, AgentType

from chain.chain import get_law_qa_chain
from config import config
from embedding.embedding import AliEmbeddings
from flow.flow import get_law_qa_flow
from handler.handler import OutCallbackHandler
from model.model import get_model_ali
from retriever.retriever import get_es_retriever
from tool.tool import get_law_documents_retriever_tool


graph = None

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

def init_law_flow():
    global graph
    graph = get_law_qa_flow()
    return graph


async def chat(message, history):
    # chain = init_law_agent()
    # out_callback = OutCallbackHandler()
    # task = asyncio.create_task(
    #     chain.ainvoke({"question": message}, config={"callbacks": [out_callback]}))

    global graph
    config = {"configurable": {"thread_id": "1"}}
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
    init_law_flow()
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


def run_web() -> None:
    import gradio as gr
    init_law_flow()
    demo = gr.ChatInterface(
        fn=chat, type="messages", examples=["故意杀了一个人，会判几年？", "杀人自首会减刑吗？"], title="法律AI小助手")

    demo.queue()
    demo.launch(
        server_name=config.WEB_HOST, server_port=config.WEB_PORT,
        auth=(config.WEB_USERNAME, config.WEB_PASSWORD),
        auth_message="默认用户名密码: username / password")


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

    if len(sys.argv) <= 1:
        parser.print_help()
        exit()

    args = parser.parse_args()
    if args.shell:
        asyncio.run(run_shell())
    if args.web:
        run_web()
