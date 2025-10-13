from langchain_core.prompts import PromptTemplate, ChatPromptTemplate, SystemMessagePromptTemplate

REACT_AGENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个专业的律师。使用工具来解答用户咨询的法律问题。
请严格按照以下格式回答:
思考: 需要分析问题并决定使用哪个工具
行动: 工具名称
行动输入: 工具输入
观察: 工具返回的结果
... (这个循环可以重复多次)
思考: 现在有足够信息来回答问题了
final_answer: 最终的回答""")
])

check_law_prompt_template = """你是一个专业律师，请根据上下文判断用户提出的问题是否和法律相关，相关请回答 Legal，不相关请回答 None Legal，不允许其它回答，不允许在答案中添加编造成分。
问题: {question}
"""

CHECK_LAW_PROMPT = SystemMessagePromptTemplate.from_template(
    template=check_law_prompt_template, input_variables=["question"]
)

hypo_questions_prompt_template = """生成 5 个假设问题的列表，以下文档可用于回答这些问题:\n\n{context}"""

HYPO_QUESTION_PROMPT = PromptTemplate(
    template=hypo_questions_prompt_template, input_variables=["context"]
)

multi_query_prompt_template = """你是一个专业的律师，您的任务是生成给定用户问题的3个不同版本，以从矢量数据库中检索相关文档。通过对用户问题生成多个视角，您的目标是帮助用户克服基于距离的相似性搜索的一些限制。提供这些用换行符分隔的替代问题，不要给出多余的回答。问题：{question}"""  # noqa
MULTI_QUERY_PROMPT_TEMPLATE = PromptTemplate(
    template=multi_query_prompt_template, input_variables=["question"]
)
