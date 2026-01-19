"""Store DB Node - From DESIGN.md"""
from datetime import datetime
from typing import Any
import structlog

from ..tools.postgresql_client import get_postgresql_client

logger = structlog.get_logger(__name__)


async def store_db_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    STORE_DB Node - From DESIGN.md
    Writes audit event to PostgreSQL (sync for durability).

    Input: Formatted log from format_log
    Output: Storage confirmation
    """
    logger.info(
        "Storing audit event to PostgreSQL",
        task_id=state.get("task_id"),
        event_id=state.get("event_id"),
    )

    task_type = state.get("task_type", "log_event")
    pg_client = get_postgresql_client()

    # Handle different task types
    if task_type == "get_timeline":
        # Query timeline instead of storing
        incident_id = state.get("incident_id")
        if not incident_id:
            return {
                "stage": "store_db",
                "db_stored": False,
                "db_store_error": "No incident_id provided for timeline query",
                "timeline_events": [],
                "timeline_count": 0,
            }

        events = await pg_client.get_incident_timeline(incident_id)

        logger.info(
            "Timeline retrieved",
            incident_id=incident_id,
            event_count=len(events),
        )

        return {
            "stage": "store_db",
            "db_stored": True,
            "timeline_events": events,
            "timeline_count": len(events),
        }

    elif task_type == "generate_report":
        # Generate compliance report
        start_date_str = state.get("report_start_date")
        end_date_str = state.get("report_end_date")

        # Parse dates
        try:
            start_date = datetime.fromisoformat(start_date_str) if start_date_str else datetime.utcnow().replace(day=1)
            end_date = datetime.fromisoformat(end_date_str) if end_date_str else datetime.utcnow()
        except ValueError:
            start_date = datetime.utcnow().replace(day=1)
            end_date = datetime.utcnow()

        report_data = await pg_client.generate_compliance_report(
            start_date=start_date,
            end_date=end_date,
            include_llm_decisions=True,
        )

        logger.info(
            "Compliance report generated",
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            incident_count=report_data.get("incident_count", 0),
        )

        return {
            "stage": "store_db",
            "db_stored": True,
            "report_data": report_data,
        }

    else:
        # Store audit event (log_event task)
        formatted_log = state.get("formatted_log", {})

        if not formatted_log:
            return {
                "stage": "store_db",
                "db_stored": False,
                "db_store_error": "No formatted log to store",
            }

        # Parse timestamp
        timestamp_str = formatted_log.get("timestamp")
        try:
            timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.utcnow()
        except ValueError:
            timestamp = datetime.utcnow()

        stored = await pg_client.insert_audit_event(
            event_id=formatted_log.get("event_id", state.get("event_id")),
            timestamp=timestamp,
            incident_id=formatted_log.get("incident_id"),
            agent_name=formatted_log.get("agent_name", "unknown"),
            node_name=formatted_log.get("node_name"),
            event_type=formatted_log.get("event_type", "state_change"),
            payload=formatted_log.get("payload", {}),
            previous_state=formatted_log.get("previous_state"),
            new_state=formatted_log.get("new_state"),
            decision_type=formatted_log.get("decision_type"),
            decision_reasoning=formatted_log.get("decision_reasoning"),
            actor=formatted_log.get("actor", "system"),
        )

        if stored:
            logger.info(
                "Audit event stored to PostgreSQL",
                event_id=state.get("event_id"),
            )
            return {
                "stage": "store_db",
                "db_stored": True,
            }
        else:
            return {
                "stage": "store_db",
                "db_stored": False,
                "db_store_error": "Failed to insert into PostgreSQL",
            }
