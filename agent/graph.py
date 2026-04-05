from langchain.globals import set_verbose, set_debug
from langchain_groq.chat_models import ChatGroq
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.prebuilt import create_react_agent

from agent.prompts import planner_prompt, architect_prompt, coder_system_prompt
from agent.states import AppState, Plan, TaskPlan
from agent.tools import write_file, read_file, get_current_directory, list_files, init_project_root

set_debug(False)
set_verbose(False)

def get_llm(api_key: str):
    # Fallback to model provided or default if needed
    if not api_key:
        raise ValueError("API Key is required to run the agent!")
    return ChatGroq(model="llama-3.1-70b-versatile", api_key=api_key)

def planner_node(state: AppState) -> AppState:
    """Converts user prompt into a structured Plan."""
    state.logs.append("Planner Agent: Analyzing user prompt...")
    llm = get_llm(state.api_key)
    resp = llm.with_structured_output(Plan).invoke(
        planner_prompt(state.user_prompt)
    )
    if resp is None:
        raise ValueError("Planner did not return a valid response.")
    state.plan = resp
    state.logs.append(f"Planner Agent: Created plan for {resp.name}")
    return state

def architect_node(state: AppState) -> AppState:
    """Creates TaskPlan from Plan."""
    state.logs.append("Architect Agent: Breaking down the plan into tasks...")
    llm = get_llm(state.api_key)
    resp = llm.with_structured_output(TaskPlan).invoke(
        architect_prompt(plan=state.plan.model_dump_json())
    )
    if resp is None:
        raise ValueError("Architect did not return a valid response.")
    
    state.task_plan = resp
    state.logs.append(f"Architect Agent: Generated {len(resp.implementation_steps)} implementation steps.")
    return state

def coder_node(state: AppState) -> AppState:
    """LangGraph tool-using coder agent."""
    init_project_root()
    steps = state.task_plan.implementation_steps
    
    if state.current_step_idx >= len(steps):
        state.status = "DONE"
        state.logs.append("Coder Agent: All implementation steps completed.")
        return state

    current_task = steps[state.current_step_idx]
    state.logs.append(f"Coder Agent: Executing step {state.current_step_idx + 1}/{len(steps)} -> {current_task.task_description}")
    
    existing_content = read_file.run(current_task.filepath)
    
    system_prompt = coder_system_prompt()
    user_prompt = (
        f"Task: {current_task.task_description}\n"
        f"File: {current_task.filepath}\n"
        f"Existing content:\n{existing_content}\n"
        "Use write_file(path, content) to save your changes."
    )

    coder_tools = [read_file, write_file, list_files, get_current_directory]
    llm = get_llm(state.api_key)
    react_agent = create_react_agent(llm, coder_tools)

    react_agent.invoke({"messages": [{"role": "system", "content": system_prompt},
                                     {"role": "user", "content": user_prompt}]})

    state.current_step_idx += 1
    state.logs.append(f"Coder Agent: Finished step {state.current_step_idx}.")
    return state

def should_continue(state: AppState):
    if state.status == "DONE":
        return END
    return "coder"

graph = StateGraph(AppState)

graph.add_node("planner", planner_node)
graph.add_node("architect", architect_node)
graph.add_node("coder", coder_node)

graph.add_edge("planner", "architect")
graph.add_edge("architect", "coder")
graph.add_conditional_edges("coder", should_continue)

graph.set_entry_point("planner")

# Compile graph
coding_agent = graph.compile()
