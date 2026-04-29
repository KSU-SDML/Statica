from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import direct_candidates_analysis, llm_analysis, cascading_candidates_analysis, output

def statica_agent():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("direct_candidates_analysis", direct_candidates_analysis)
    workflow.add_node("llm_analysis", llm_analysis)
    workflow.add_node("cascading_candidates_analysis", cascading_candidates_analysis)
    workflow.add_node("output", output)

    workflow.set_entry_point("direct_candidates_analysis")

    workflow.add_edge("direct_candidates_analysis", "llm_analysis")
    workflow.add_edge("llm_analysis", "cascading_candidates_analysis")
    workflow.add_edge("cascading_candidates_analysis", "output")
    workflow.add_edge("output", END)

    return workflow.compile()
