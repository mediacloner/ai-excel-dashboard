from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, StateGraph

from app.config import get_config
from app.models.state import GraphState
from app.pipeline.nodes.generate_dict import generate_dictionary
from app.pipeline.nodes.import_db import import_to_db
from app.pipeline.nodes.ingest import ingest_excel
from app.pipeline.nodes.map_headers import map_headers
from app.pipeline.nodes.profile import profile_data


def build_pipeline() -> StateGraph:
    workflow = StateGraph(GraphState)

    # Add nodes
    workflow.add_node("ingest_excel", ingest_excel)
    workflow.add_node("profile_data", profile_data)
    workflow.add_node("map_headers", map_headers)
    workflow.add_node("generate_dictionary", generate_dictionary)
    workflow.add_node("import_to_db", import_to_db)

    # Define edges
    workflow.set_entry_point("ingest_excel")
    workflow.add_edge("ingest_excel", "profile_data")
    workflow.add_edge("profile_data", "map_headers")
    workflow.add_edge("map_headers", "generate_dictionary")
    workflow.add_edge("generate_dictionary", "import_to_db")
    workflow.add_edge("import_to_db", END)

    return workflow


async def get_compiled_pipeline():
    config = get_config()
    workflow = build_pipeline()

    checkpointer = AsyncSqliteSaver.from_conn_string(config.langgraph.checkpoint_db)

    # Interrupt before import_to_db for human review
    compiled = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["import_to_db"],
    )

    return compiled
