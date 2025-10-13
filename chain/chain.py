from operator import itemgetter

from langchain.agents import AgentExecutor, initialize_agent, AgentType
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda, RunnableBranch
from embedding.embedding import AliEmbeddings
from model.model import get_model_ali
from prompt.prompt import CHECK_LAW_PROMPT
from retriever.retriever import get_es_retriever
from tool.tool import get_law_documents_retriever_tool


def _get_non_legal_response() -> str:
    """返回非法律问题的标准回复"""
    responses = [
        "抱歉，我是一个专门的法律智能助手，只能回答与法律相关的问题。请问您有什么法律方面的疑问吗？",
        "您的问题超出了我的专业范围。我专注于提供法律法规、案例解读等法律咨询服务。",
        "作为法律助手，我无法回答非法律相关问题。如果您有法律方面的困惑，我很乐意为您解答。",
        "我主要处理法律领域的咨询，如合同纠纷、劳动争议、婚姻家事等。请问您有这方面的需求吗？"
    ]
    import random
    return random.choice(responses)


def _debug_fn(x):
    print(x)
    return x


def get_law_qa_chain(law_agent: AgentExecutor, checker_model: BaseChatModel):
    chain = ({
                 "question": RunnableLambda(lambda x: x["question"]),
                 "is_legal_question": CHECK_LAW_PROMPT | checker_model | StrOutputParser(),
             }
             # | RunnableLambda(_debug_fn)
             | RunnableBranch(
                (lambda x: x["is_legal_question"] == "Legal",
                 RunnableLambda(lambda x: {"input": x["question"]}) | law_agent),
                (RunnableLambda(lambda x: {"output": _get_non_legal_response()})),
            ))
    return chain


if __name__ == '__main__':
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
    print(chain.invoke(
        {"question": "室友想要我陪他睡觉，我不同意，室友苦苦相逼，情急之下我一失手用刀将室友杀死，我会怎么样"}))
    print(chain.invoke(
        {
            "question": "我骑车正常行驶在正确的非机动车道上，在通过一个路口时慢行并左右观察确认无异常时通过了，但是此时从对面突然冲出来一个小孩，我无法立即刹车因此将他撞倒，我需要承担责任吗？"}))
