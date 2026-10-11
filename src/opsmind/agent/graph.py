from langgraph.graph import END, START, StateGraph

from opsmind.agent.graph_state import GraphState
from opsmind.agent.nodes import GraphNodes


def next_node(state: GraphState) -> str:
    if state["status"] == "waiting_confirmation":
        return "approval"
    if state["status"] == "running":
        return "model"
    if state["status"] == "apply":
        return "tools" if state["turn"]["call"] else "finalize"
    return END


def build_graph(runtime, saver):
    nodes = GraphNodes(runtime)
    graph = StateGraph(GraphState)
    graph.add_node("sync", nodes.sync)
    graph.add_node("model", nodes.model)
    graph.add_node("tools", nodes.apply)
    graph.add_node("finalize", nodes.apply)
    graph.add_node("approval", nodes.approval)
    graph.add_edge(START, "sync")
    for name in ("sync", "model", "tools", "approval"):
        graph.add_conditional_edges(name, next_node)
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=saver)
