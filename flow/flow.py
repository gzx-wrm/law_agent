from typing import Annotated
import random

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import add_messages
from langgraph.prebuilt import create_react_agent, tools_condition
from langgraph.types import Command
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from embedding.embedding import AliEmbeddings
from model.model import get_model_ali, get_langgraph_model
from prompt.prompt import REACT_AGENT_PROMPT, CHECK_LAW_PROMPT
from retriever.retriever import get_es_retriever, get_multi_query_retriever
from tool.tool import get_law_documents_retriever_tool


class State(TypedDict):
    messages: Annotated[list, add_messages]
    check_legal_question_prompt: BaseMessage
    is_legal_question: bool

# 节点名常量
NODE_FORMAT_CHECK_LEGAL_PROMPT = "format_check_legal_prompt"
NODE_CHECK_LEGAL_QUESTION = "check_legal_question"
NODE_LAW_AGENT = "law_agent"
NODE_GET_NON_LEGAL_RESPONSE = "get_non_legal_response"

def get_law_qa_flow(with_memory=False, use_multi_query_retriever=True):
    graph_builder = StateGraph(State)

    llm = get_langgraph_model()
    embedding = AliEmbeddings()
    law_retriever = get_es_retriever("law_documents", embedding)
    if use_multi_query_retriever:
        law_retriever = get_multi_query_retriever(law_retriever, llm)

    retriever_tool = get_law_documents_retriever_tool(law_retriever)

    agent = create_react_agent(model=llm, tools=[retriever_tool])

    def update_state(**kwargs) -> dict:
        state_update = {}
        for key, value in kwargs.items():
            state_update[key] = value
        return state_update

    def call_arbitrary_model(state):
        """Example node that calls an arbitrary model and streams the output"""
        writer = get_stream_writer()
        # Assume you have a streaming client that yields chunks
        assistant_message = None
        for chunk in agent.stream(state, stream_mode=["messages", "updates"]):
            # print(chunk)
            # 提取llm最终的回复，通过return保存到state中
            if (chunk[0] == "updates" and
                    isinstance(chunk[1], dict) and
                    "agent" in chunk[1] and
                    chunk[1]["agent"]["messages"][0].content != ""):
                assistant_message = chunk[1]["agent"]["messages"]
            writer({"llm_chunk": chunk})
        return {"messages": assistant_message}

    def format_check_legal_prompt(state):
        prompt = CHECK_LAW_PROMPT.format_messages(question=state["messages"][-1].content)
        return Command(update=update_state(check_legal_question_prompt=prompt[0]))

    def check_legal_question(state):
        messages = [state["check_legal_question_prompt"]]
        messages = add_messages(messages, state["messages"])
        res = llm.invoke(messages)
        return Command(update=update_state(is_legal_question=(res.content == "Legal")))

    def agent_route(state):
        if state["is_legal_question"]:
            return NODE_LAW_AGENT
        else:
            return NODE_GET_NON_LEGAL_RESPONSE

    def get_non_legal_response(state):
        """返回非法律问题的标准回复"""
        responses = [
            "抱歉，我是一个专门的法律智能助手，只能回答与法律相关的问题。请问您有什么法律方面的疑问吗？",
            "您的问题超出了我的专业范围。我专注于提供法律法规、案例解读等法律咨询服务。",
            "作为法律助手，我无法回答非法律相关问题。如果您有法律方面的困惑，我很乐意为您解答。",
            "我主要处理法律领域的咨询，如合同纠纷、劳动争议、婚姻家事等。请问您有这方面的需求吗？"
        ]
        writer = get_stream_writer()
        # Assume you have a streaming client that yields chunks
        writer({"llm_chunk": ("messages", (AIMessage(content=random.choice(responses)),))})
        return {"result": "completed"}

    graph_builder.add_node(NODE_FORMAT_CHECK_LEGAL_PROMPT, format_check_legal_prompt)
    graph_builder.add_node(NODE_CHECK_LEGAL_QUESTION, check_legal_question)
    graph_builder.add_node(NODE_LAW_AGENT, call_arbitrary_model)
    graph_builder.add_node(NODE_GET_NON_LEGAL_RESPONSE, get_non_legal_response)

    # Any time a tool is called, we return to the chatbot to decide the next step
    graph_builder.add_edge(START, NODE_FORMAT_CHECK_LEGAL_PROMPT)
    graph_builder.add_edge(NODE_FORMAT_CHECK_LEGAL_PROMPT, NODE_CHECK_LEGAL_QUESTION)
    graph_builder.add_conditional_edges(NODE_CHECK_LEGAL_QUESTION, agent_route,
                                        {NODE_LAW_AGENT: NODE_LAW_AGENT, NODE_GET_NON_LEGAL_RESPONSE: NODE_GET_NON_LEGAL_RESPONSE})
    graph_builder.add_edge(NODE_LAW_AGENT, END)
    graph_builder.add_edge(NODE_GET_NON_LEGAL_RESPONSE, END)
    graph = graph_builder.compile(checkpointer=InMemorySaver())

    return graph

    for chunk in graph.stream(
            {"messages": [{"role": "user",
                           # "content": "我骑车正常行驶在正确的非机动车道上，在通过一个路口时慢行并左右观察确认无异常时通过了，但是此时从对面突然冲出来一个小孩，我无法立即刹车因此将他撞倒，我需要承担责任吗？"}]},
                           "content": "今天天气如何？"}]},
            stream_mode=["messages", "custom"],
            subgraphs=True):
        if chunk[1] == "messages":
            continue
        chunk = chunk[2]["llm_chunk"]
        if chunk[0] != "messages":
            continue
        chunk = chunk[1][0]
        if chunk.content == "":
            continue
        print(chunk.content, end="")


def test():
    graph_builder = StateGraph(State)

    llm = get_langgraph_model()
    embedding = AliEmbeddings()
    law_retriever = get_es_retriever("law_documents", embedding)
    retriever_tool = get_law_documents_retriever_tool(law_retriever)
    tools = [retriever_tool]
    # llm_with_tools = llm.bind_tools(tools)
    # for chunk in llm_with_tools.stream("我骑车正常行驶在正确的非机动车道上，在通过一个路口时慢行并左右观察确认无异常时通过了，但是此时从对面突然冲出来一个小孩，我无法立即刹车因此将他撞倒，我需要承担责任吗？"):
    #     print(chunk)

    agent = create_react_agent(model=llm, tools=[retriever_tool])

    # def chatbot(state: State):
    #     return {"messages": [llm_with_tools.stream(state["messages"])]}
    # return {"messages": [llm_with_tools.invoke(state["messages"])]}

    # graph_builder.add_node("chatbot", chatbot)
    graph_builder.add_node("law_agent", agent)
    # tool_node = ToolNode(tools=tools)
    # graph_builder.add_node("tools", tool_node)

    graph_builder.add_conditional_edges(
        "chatbot",
        tools_condition,
    )
    # Any time a tool is called, we return to the chatbot to decide the next step
    graph_builder.add_edge("tools", "chatbot")
    graph_builder.add_edge(START, "chatbot")
    graph = graph_builder.compile()

    # for event in graph.stream({"messages": [{"role": "user", "content": "我骑车正常行驶在正确的非机动车道上，在通过一个路口时慢行并左右观察确认无异常时通过了，但是此时从对面突然冲出来一个小孩，我无法立即刹车因此将他撞倒，我需要承担责任吗？"}]}):
    #     for value in event.values():
    #         print("Assistant:", value["messages"][-1].content)
    # print(graph.invoke({"messages": [{"role": "user", "content": "我骑车正常行驶在正确的非机动车道上，在通过一个路口时慢行并左右观察确认无异常时通过了，但是此时从对面突然冲出来一个小孩，我无法立即刹车因此将他撞倒，我需要承担责任吗？"}]}))


if __name__ == '__main__':
    # agent = get_qa_flow()
    # print(agent.invoke({"messages": [{"role": "user", "content": "我骑车正常行驶在正确的非机动车道上，在通过一个路口时慢行并左右观察确认无异常时通过了，但是此时从对面突然冲出来一个小孩，我无法立即刹车因此将他撞倒，我需要承担责任吗？"}]}))
    test()
    pass