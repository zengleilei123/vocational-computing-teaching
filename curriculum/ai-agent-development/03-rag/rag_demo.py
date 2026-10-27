"""A tiny, dependency-free retrieval baseline for teaching RAG concepts.

This is keyword retrieval, not embedding-based semantic search and not a full
LLM RAG pipeline. It returns matched evidence and explicit source labels.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    title: str
    source: str
    content: str
    keywords: tuple[str, ...]


DOCUMENTS = (
    Document(
        title="Python 课程学习顺序",
        source="curriculum/python-programming/01-basics/README.md",
        content="建议先学习 Python 基础，再学习数据结构与算法、SQL 与数据库，之后学习 API 与 AI 应用开发。",
        keywords=("python", "学习顺序", "先学什么", "数据结构", "sql", "数据库"),
    ),
    Document(
        title="工具调用的安全边界",
        source="curriculum/ai-agent-development/02-llm-tool-calling/README.md",
        content="模型只能提出工具调用请求；应用程序必须校验工具名和参数，只执行白名单工具，并限制执行轮数。",
        keywords=("工具调用", "白名单", "参数校验", "安全", "执行轮数", "agent"),
    ),
    Document(
        title="智能体课程项目",
        source="curriculum/ai-agent-development/README.md",
        content="课程助教智能体可以查询课程资料、执行低风险工具、展示回答依据，并通过固定测试集评估任务成功率。",
        keywords=("智能体", "课程助教", "评测", "任务成功率", "课程资料"),
    ),
)


@dataclass(frozen=True)
class RetrievalResult:
    document: Document
    score: int


def retrieve(query: str, top_k: int = 3) -> list[RetrievalResult]:
    """Rank documents by matching manually curated keyword phrases."""
    if not isinstance(query, str) or not query.strip():
        return []
    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    normalized = query.casefold()
    results = []
    for document in DOCUMENTS:
        score = sum(1 for keyword in document.keywords if keyword.casefold() in normalized)
        if score:
            results.append(RetrievalResult(document=document, score=score))
    results.sort(key=lambda item: (-item.score, item.document.title))
    return results[:top_k]


def answer_with_sources(query: str, min_score: int = 1) -> str:
    """Return retrieved evidence; refuse to answer when no evidence is found."""
    if min_score < 1:
        raise ValueError("min_score must be at least 1")
    results = retrieve(query)
    if not results or results[0].score < min_score:
        return "当前课程资料中没有检索到足够依据，请补充资料或转人工核对。"

    lines = ["根据检索到的课程资料："]
    for result in results:
        if result.score < min_score:
            continue
        doc = result.document
        lines.append(f"- {doc.content}（来源：{doc.title}；文件：{doc.source}）")
    return "\n".join(lines)


def main() -> None:
    print("课程知识库检索演示（关键词检索基线，输入 q 退出）")
    while True:
        query = input("\n问题：").strip()
        if query.casefold() in {"q", "quit", "exit"}:
            break
        print(answer_with_sources(query))


if __name__ == "__main__":
    main()
