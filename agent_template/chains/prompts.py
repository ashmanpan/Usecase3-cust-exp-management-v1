"""
Prompt Templates for Agent Chains

Reusable prompts for common patterns across agents.
Customize these for agent-specific behavior.
"""

# ============== Checklist Generation ==============

CHECKLIST_GENERATION_PROMPT = """You are a network operations expert.
Given a task, generate a checklist of items that need to be verified or processed.

Task ID: {task_id}
Input Data: {input_payload}
User Request: {user_prompt}

Generate a numbered checklist of specific items to verify or process.
Each item should be:
1. Specific and actionable
2. Verifiable with available tools
3. Focused on one aspect

Output ONLY the numbered list, nothing else.
Example:
1. Verify BGP neighbor state for PE-SJ-01
2. Check route advertisement to PE-NY-01
3. Validate path metrics
"""

# ============== Evaluation ==============

EVALUATION_PROMPT = """Evaluate the current workflow progress.

Task ID: {task_id}
Analysis: {analysis}
Current Iteration: {iteration}/{max_iterations}

Based on the analysis:
1. Is the task complete? (yes/no)
2. What is your confidence level? (0-100%)
3. What action should be taken next?

If the task is NOT complete and we haven't reached max iterations,
respond with "needs_more_work" and explain what's missing.

If the task IS complete or we've done enough iterations,
respond with "complete" and summarize the findings.
"""

# ============== Analysis ==============

ANALYSIS_PROMPT = """Analyze the tool outputs and provide insights.

Task ID: {task_id}

Tool Outputs:
{tool_outputs}

Raw Result:
{raw_result}

Provide a structured analysis including:
1. Key findings from the tool outputs
2. Any anomalies or issues detected
3. Recommendations for next steps
4. Summary conclusion

Be specific and reference actual data from the outputs.
"""

# ============== A2A Task Delegation ==============

A2A_TASK_PROMPT = """You need to delegate a task to another agent.

Available Agents and Their Capabilities:
{agent_capabilities}

Current Task:
{current_task}

Context:
{context}

Determine:
1. Which agent should handle this task?
2. What specific task type should be requested?
3. What payload data should be included?

Respond in JSON format:
{{
    "target_agent": "agent_name",
    "task_type": "task_type",
    "payload": {{...}},
    "priority": 1-10,
    "reasoning": "why this agent"
}}
"""

# ============== Service Impact Assessment ==============

SERVICE_IMPACT_PROMPT = """Assess the service impact from the following network degradation.

Incident ID: {incident_id}
Degraded Links: {degraded_links}

Service Data:
{service_data}

For each affected service, determine:
1. Service ID and customer
2. SLA tier (platinum/gold/silver/bronze)
3. Impact severity (critical/major/minor)
4. Current SLA metrics vs thresholds
5. Recommended action priority

Output a structured assessment with services ordered by impact severity.
"""

# ============== Path Computation ==============

PATH_COMPUTATION_PROMPT = """Compute an alternate path avoiding degraded links.

Incident ID: {incident_id}
Source PE: {source_pe}
Destination PE: {destination_pe}
Avoid Links: {avoid_links}
Constraints: {constraints}

Topology Data:
{topology}

Find the best alternate path that:
1. Avoids all degraded links
2. Meets the specified constraints
3. Minimizes latency and IGP metric
4. Has sufficient bandwidth

Output the path as an ordered list of nodes and links with metrics.
"""

# ============== Tunnel Provisioning ==============

TUNNEL_PROVISION_PROMPT = """Prepare tunnel provisioning for protection path.

Incident ID: {incident_id}
Service ID: {service_id}
TE Type: {te_type}
Head End: {head_end}
Tail End: {tail_end}
Computed Path: {computed_path}

Generate the CNC API payload for tunnel provisioning.
Include:
1. Tunnel name following convention
2. Path segments/SIDs
3. Binding SID allocation
4. Priority settings

Output the complete API payload in JSON format.
"""

# ============== Alert Correlation ==============

ALERT_CORRELATION_PROMPT = """Correlate incoming network alerts.

Raw Alerts:
{raw_alerts}

Existing Incidents:
{existing_incidents}

Correlation Rules:
1. Alerts affecting same link within 5 minutes are related
2. Multiple alerts from same source may indicate flapping
3. Alerts propagating across topology may have common root cause

Determine:
1. Which alerts should be correlated together
2. Whether this creates a new incident or updates existing
3. Flap detection status
4. Root cause hypothesis

Output correlation decision with reasoning.
"""

# ============== Restoration Monitoring ==============

RESTORATION_PROMPT = """Monitor original path for SLA recovery.

Incident ID: {incident_id}
Protection Tunnel: {protection_tunnel}
Original Path Links: {original_links}
SLA Tier: {sla_tier}
Current Metrics: {current_metrics}
SLA Thresholds: {thresholds}

Check if:
1. All original path links are up
2. SLA metrics are within thresholds
3. Metrics have been stable for hold timer period

Determine restoration status and recommended action:
- continue_monitoring: Still degraded
- start_hold_timer: Links up, begin observation
- ready_for_cutover: Stable and ready for traffic return
- cutover_in_progress: Gradual traffic migration underway
"""
