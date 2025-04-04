"""
Module for generating AI-powered insights using Google's Gemini 2.0 model.
"""
import os
import logging
import json
import re
import base64
import google.generativeai as genai
from google.generativeai import types
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import datetime as dt

from config import app_config
from data_processor import DataProcessor

# Configure logging
logging.basicConfig(
    level=getattr(logging, app_config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configure Gemini API - Use the provided key directly (UNSAFE FOR PRODUCTION)
GEMINI_API_KEY_PROVIDED = "AIzaSyARZyERqMaFInsbRKUA0NxOok77syBNzK8"
if GEMINI_API_KEY_PROVIDED:
    genai.configure(api_key=GEMINI_API_KEY_PROVIDED)
    logger.info("Configured Gemini API using the hardcoded key.")
else:
    # Fallback to environment variable if hardcoded key is somehow empty
    GEMINI_API_KEY_ENV = os.getenv("GEMINI_API_KEY")
    if GEMINI_API_KEY_ENV:
        genai.configure(api_key=GEMINI_API_KEY_ENV)
        logger.info("Configured Gemini API using environment variable key as fallback.")
    else:
        logger.warning("Gemini API key not found (neither hardcoded nor in environment).")

# Check if API key is available and likely valid
API_KEY_USED = GEMINI_API_KEY_PROVIDED or os.getenv("GEMINI_API_KEY")
API_KEY_VALID = bool(API_KEY_USED and len(API_KEY_USED) > 20 and API_KEY_USED.startswith("AIza"))

# Define standard response for rate limiting
RATE_LIMIT_RESPONSE = {
    "executive_summary": "Unable to generate AI insights due to API rate limiting.",
    "key_metrics": "The Gemini API quota has been exceeded. Please try again later.",
    "risks_bottlenecks": "API rate limit reached. Consider implementing a retry mechanism with exponential backoff.",
    "recommendations": "1. Check Gemini API quota and billing details at https://ai.google.dev/gemini-api/docs/rate-limits\n2. Implement request caching to reduce API calls\n3. Consider upgrading to a higher API tier",
    "team_performance": "Team performance analysis unavailable due to API rate limiting."
}

class AIInsightsGenerator:
    """Generate insights from YouTrack data using Google's Gemini 2.0 AI model."""

    def __init__(self, model_name: str = "gemini-2.0-flash", generation_config: Optional[Dict] = None, safety_settings: Optional[Dict] = None):
        """Initialize with model configuration."""
        if not API_KEY_VALID:
             raise ValueError("Gemini API key is invalid or missing. Cannot initialize AIInsightsGenerator.")

        self.model_name = model_name
        # Default safety settings (adjust as needed)
        default_safety_settings = {
            types.HarmCategory.HARM_CATEGORY_HARASSMENT: types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        }
        # Default generation config (adjust as needed)
        default_generation_config = {
             "temperature": 0.6, # Balance creativity and coherence
             "top_p": 0.95,
             "top_k": 40,
             "max_output_tokens": 8192, # Generous limit for analysis + code
             "response_mime_type": "text/plain", # Default, can be overridden for specific calls if needed
        }

        self.safety_settings = safety_settings if safety_settings is not None else default_safety_settings
        self.generation_config_dict = generation_config if generation_config is not None else default_generation_config

        try:
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                safety_settings=self.safety_settings,
                # Pass generation_config dict directly here if model supports it,
                # otherwise pass during generate_content
                # generation_config=genai.types.GenerationConfig(**self.generation_config_dict) # Check SDK docs
            )
            logger.info(f"Initialized Gemini Model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini Model: {e}", exc_info=True)
            raise

    def _cleanse_before_json(self, data: Any) -> Any:
        """
        Recursively cleanses data structures to ensure JSON serializability.
        Handles dicts, lists, numpy types, datetime, pd.Timestamp, NaN, NaT.
        """
        if isinstance(data, dict):
            # Cleanse dictionary keys and values
            clean_dict = {}
            for k, v in data.items():
                # Ensure keys are strings, attempt conversion if not
                clean_key = str(k) if not isinstance(k, str) else k
                clean_dict[clean_key] = self._cleanse_before_json(v)
            return clean_dict
        elif isinstance(data, (list, tuple)):
            # Cleanse list/tuple items
            return [self._cleanse_before_json(item) for item in data]
        elif isinstance(data, (datetime, date, pd.Timestamp)):
            # Convert datetime/date/Timestamp to ISO string
            # Check for NaT (Not a Time) specifically for pandas Timestamps
            if pd.isna(data):
                 return None
            return data.isoformat()
        elif isinstance(data, (np.integer, np.int64)):
            # Convert numpy integers to Python int
            return int(data)
        elif isinstance(data, (np.floating, np.float64)):
            # Convert numpy floats to Python float, handle NaN
            return None if np.isnan(data) else float(data)
        elif isinstance(data, np.bool_):
            # Convert numpy bool to Python bool
            return bool(data)
        elif isinstance(data, np.ndarray):
            # Convert numpy arrays to lists, applying cleansing to elements
            return self._cleanse_before_json(data.tolist())
        elif isinstance(data, float) and np.isnan(data):
             # Handle standard Python float NaN
             return None
        elif pd.isna(data):
             # General Pandas NA check (covers NaT again and potentially others)
             return None
        # Add handling for other non-serializable types if necessary
        # For example, sets:
        # elif isinstance(data, set):
        #     return self._cleanse_before_json(list(data))
        else:
            # Assume the data is already serializable
            return data

    def _summarize_closed_issues(self, data_processor) -> Dict[str, Any]:
        """
        Generate a concise summary of closed/resolved issues to optimize token usage.

        Args:
            data_processor: DataProcessor instance with loaded data

        Returns:
            Dictionary with aggregated data about closed issues
        """
        logger.info("Generating summary for closed issues...")
        summary = {}

        try:
            if data_processor.issues_df is not None and not data_processor.issues_df.empty:
                # Get resolved/closed issues and explicitly create a copy
                resolved_issues = data_processor.issues_df[data_processor.issues_df['resolved'].notna()].copy()

                if not resolved_issues.empty:
                    # Get resolution time statistics
                    if 'created' in resolved_issues.columns and 'resolved' in resolved_issues.columns:
                        # Use .loc for safer assignment
                        resolved_issues.loc[:, 'resolution_time'] = resolved_issues['resolved'] - resolved_issues['created']
                        avg_days = resolved_issues['resolution_time'].mean().total_seconds() / (24 * 3600)
                        median_days = resolved_issues['resolution_time'].median().total_seconds() / (24 * 3600)
                        max_days = resolved_issues['resolution_time'].max().total_seconds() / (24 * 3600)
                        min_days = resolved_issues['resolution_time'].min().total_seconds() / (24 * 3600)

                        summary['resolution_stats'] = {
                            'count': len(resolved_issues),
                            'avg_days': round(avg_days, 2),
                            'median_days': round(median_days, 2),
                            'max_days': round(max_days, 2),
                            'min_days': round(min_days, 2)
                        }

                    # Monthly resolution counts
                    if 'resolved' in resolved_issues.columns:
                        # Group by month and count
                        # Use .loc for safer assignment
                        resolved_issues.loc[:, 'month'] = resolved_issues['resolved'].dt.strftime('%Y-%m')
                        monthly_counts = resolved_issues.groupby('month').size().to_dict()

                        # Get the last 6 months of data
                        sorted_months = sorted(monthly_counts.keys())
                        recent_months = sorted_months[-6:] if len(sorted_months) > 6 else sorted_months

                        summary['monthly_resolutions'] = {month: monthly_counts[month] for month in recent_months}

                    # Status distribution
                    if (data_processor.custom_fields_df is not None and
                        not data_processor.custom_fields_df.empty):

                        # Get only the closed issues' custom fields
                        closed_issue_ids = resolved_issues['id'].tolist()
                        closed_custom_fields = data_processor.custom_fields_df[
                            data_processor.custom_fields_df['issue_id'].isin(closed_issue_ids)
                        ]

                        # Status distribution for closed issues
                        if 'field_name' in closed_custom_fields.columns and 'field_value' in closed_custom_fields.columns:
                            status_field = closed_custom_fields[closed_custom_fields['field_name'] == 'State']
                            if not status_field.empty:
                                summary['status_counts'] = status_field['field_value'].value_counts().to_dict()

                            # Priority distribution for closed issues
                            priority_field = closed_custom_fields[closed_custom_fields['field_name'] == 'Priority']
                            if not priority_field.empty:
                                summary['priority_counts'] = priority_field['field_value'].value_counts().to_dict()

                    # Assignee distribution for closed issues
                    if 'assignee' in resolved_issues.columns:
                        assignee_counts = resolved_issues['assignee'].value_counts().head(10).to_dict()
                        summary['top_assignees'] = assignee_counts

        except Exception as e:
            logger.error(f"Error generating closed issues summary: {str(e)}", exc_info=True)
            summary['error'] = str(e)

        return summary

    def _prepare_data_context(self, data_processor) -> Dict[str, Any]:
        """
        Prepare data context for the AI model, using processed data and metrics.
        Relies on _cleanse_before_json to be called *after* this method.
        """
        logger.info("Preparing data context for leadership report from processed data...")
        context = {}
        essential_fields = ['idReadable', 'summary', 'State', 'Priority', 'Assignees', 'created', 'updated', 'resolved']

        try:
            # --- 1. Use Processed Issues DataFrame --- 
            if data_processor.issues_df is not None and not data_processor.issues_df.empty:
                
                # <<< START FIX: Calculate Total Open Count BEFORE filtering >>>
                # Filter for all open issues first (resolved is NaT or NaTType)
                all_open_issues_df = data_processor.issues_df[pd.isna(data_processor.issues_df['resolved'])].copy()
                # Exclude only Cyclic from the total count if needed (assuming Cyclic is never considered open)
                # If Cyclic issues CAN be open and shouldn't be in total, add filtering here.
                # For now, assuming all non-resolved are counted unless explicitly closed/cyclic by definition.
                total_open_issues_count = len(all_open_issues_df)
                logger.info(f"Calculated total open issues (all states except closed): {total_open_issues_count}")
                # <<< END FIX >>>

                # Now, prepare the filtered snapshot for the AI's detailed analysis
                # Use the already created all_open_issues_df as the base
                open_issues_df_for_snapshot = all_open_issues_df.copy() 

                # Filter out 'To Verify' and 'Cyclic' states for the AI snapshot
                if 'State' in open_issues_df_for_snapshot.columns:
                    excluded_states = ['To Verify', 'Cyclic']
                    original_snapshot_count = len(open_issues_df_for_snapshot)
                    open_issues_df_for_snapshot = open_issues_df_for_snapshot[~open_issues_df_for_snapshot['State'].isin(excluded_states)]
                    filtered_snapshot_count = len(open_issues_df_for_snapshot)
                    logger.info(f"Filtered snapshot: Removed {original_snapshot_count - filtered_snapshot_count} issues with states {excluded_states}. AI context snapshot size: {filtered_snapshot_count}.")
                else:
                    logger.warning("'State' column not found, cannot filter 'To Verify' or 'Cyclic' for AI context snapshot.")

                # Select key fields for the context snapshot using the filtered dataframe
                cols_to_include = [col for col in essential_fields if col in open_issues_df_for_snapshot.columns]
                if 'Assignees' in open_issues_df_for_snapshot.columns and not pd.api.types.is_string_dtype(open_issues_df_for_snapshot['Assignees']):
                     open_issues_df_for_snapshot['Assignees'] = open_issues_df_for_snapshot['Assignees'].astype(str)
                for col in ['created', 'updated', 'resolved']:
                    if col in open_issues_df_for_snapshot.columns:
                       open_issues_df_for_snapshot[col] = pd.to_datetime(open_issues_df_for_snapshot[col], errors='coerce')
                
                # Assign the FILTERED snapshot to the context for the AI
                context['open_issues_snapshot'] = open_issues_df_for_snapshot[cols_to_include].to_dict(orient='records')
                
                # --- 2. Use Calculated Metrics --- 
                # Combine 24h and overall metrics, passing the CORRECT total open count
                combined_stats = {
                    'total_open_issues': total_open_issues_count, # <<< USE CORRECTED COUNT
                    'total_issues_processed': len(data_processor.issues_df), # Total including closed
                    **(data_processor.metrics_24h or {}), # Use empty dict if None
                    **(data_processor.metrics_overall or {}) # Use empty dict if None
                }
                
                # Calculate age stats based on the FILTERED snapshot if needed for context
                # (The AI prompt asks for avg age of ACTIVE issues from snapshot)
                if 'created' in open_issues_df_for_snapshot.columns and pd.api.types.is_datetime64_any_dtype(open_issues_df_for_snapshot['created']):
                    tz = open_issues_df_for_snapshot['created'].dt.tz if open_issues_df_for_snapshot['created'].dt.tz else None
                    now_aware = datetime.now(tz) 
                    open_issues_df_for_snapshot['age_days'] = (now_aware - open_issues_df_for_snapshot['created']).dt.days
                    valid_ages = open_issues_df_for_snapshot['age_days'].dropna()
                    # These specific age stats might not be directly used by prompt, but calculating anyway
                    combined_stats['average_snapshot_age_days'] = round(valid_ages.mean(), 1) if not valid_ages.empty else 0
                    combined_stats['max_snapshot_age_days'] = valid_ages.max() if not valid_ages.empty else 0
                else: 
                    logger.warning("Could not calculate issue age stats for snapshot context.")
                    combined_stats['average_snapshot_age_days'] = 0
                    combined_stats['max_snapshot_age_days'] = 0
                
                context['stats'] = combined_stats # Assign the combined dict to context
            else:
                 logger.warning("Processed Issues DataFrame is missing or empty.")
                 context['open_issues_snapshot'] = []
                 context['stats'] = {**(data_processor.metrics_24h or {}), **(data_processor.metrics_overall or {})}


            # --- 3. Use Processed Recent Activity (Last 24 hours) --- 
            activity_summary = []
            # Check existence using hasattr for safety
            if hasattr(data_processor, 'recent_activity_df') and data_processor.recent_activity_df is not None and not data_processor.recent_activity_df.empty:
                recent_activity_df = data_processor.recent_activity_df.copy()
                # Select and rename columns for clarity
                cols_to_keep = {
                    'issue_readable_id': 'issue_id',
                    'timestamp': 'time',
                    'author': 'user',
                    'field_name': 'field',
                    'added_value': 'new_value',
                    'removed_value': 'old_value',
                    'category': 'type'
                }
                valid_cols = {k: v for k, v in cols_to_keep.items() if k in recent_activity_df.columns}
                recent_activity_df = recent_activity_df[list(valid_cols.keys())].rename(columns=valid_cols)
                # Limit to top N recent activities to manage context size
                activity_summary = recent_activity_df.head(50).to_dict(orient='records') 
            context['recent_activity_summary'] = activity_summary

            # --- 4. Add Custom Field Definitions --- #
            # Check existence using hasattr for safety
            if hasattr(data_processor, 'custom_field_definitions') and data_processor.custom_field_definitions:
                 context['custom_field_definitions'] = data_processor.custom_field_definitions
            else:
                 logger.warning("Custom field definitions missing from data processor.")
                 context['custom_field_definitions'] = {}
                 
        except Exception as e:
            logger.error(f"Failed to prepare data context: {e}", exc_info=True)
            raise ValueError(f"Failed to prepare data context: {e}") from e
        
        # Return the raw context - cleansing happens just before JSON dump
        return context

    # --- NEW: Minimal Context for Plots --- 
    def _prepare_minimal_plot_context(self, data_processor) -> Dict[str, Any]:
        """Prepares only the essential data needed for plot generation."""
        minimal_context = {}
        try:
            # 1. Assignee Workload (from overall metrics)
            if hasattr(data_processor, 'metrics_overall') and data_processor.metrics_overall:
                minimal_context['assignee_workload'] = data_processor.metrics_overall.get('assignee_workload', {})
            else:
                minimal_context['assignee_workload'] = {}
                logger.warning("Assignee workload data missing for plot context.")

            # 2. Open Issue State Counts
            state_counts = {}
            if data_processor.issues_df is not None and not data_processor.issues_df.empty:
                open_issues_df = data_processor.issues_df[pd.isna(data_processor.issues_df['resolved'])].copy()
                if 'State' in open_issues_df.columns:
                     # Ensure NaN/None states are handled gracefully (e.g., map to 'Unknown')
                     state_counts = open_issues_df['State'].fillna('Unknown').value_counts().to_dict()
                else:
                    logger.warning("'State' column missing from open issues for plot context.")
            minimal_context['open_issue_state_counts'] = state_counts

        except Exception as e:
            logger.error(f"Failed to prepare minimal plot context: {e}", exc_info=True)
            # Return empty dicts on error to avoid downstream issues
            minimal_context['assignee_workload'] = {}
            minimal_context['open_issue_state_counts'] = {}

        # Cleanse this minimal context before returning
        return self._cleanse_before_json(minimal_context)
    # --- END Minimal Context --- 

    # --- Combined Analysis and Plot Code Prompt --- 
    def _create_analysis_and_plot_code_prompt(self) -> str:
        """Creates the prompt for generating text analysis AND Python plot code."""
        prompt = """
# **ROLE: Kayten's YouTrack AI Assistant for Professional Leads**
# **CONTEXT:** You are generating a daily intelligence report for project leadership within Kayten, focusing on the MQ EIS/KG BSW project.
# **EXPECTATION:** Deliver concise, actionable, **deeply analytical**, data-driven insights with professional language. **Do not just report data; interpret it, identify root causes, analyze impacts, and provide concrete recommendations.**

# TASK: Generate **Strategic Project Analysis for Leadership** and Python Plot Code
# TARGET AUDIENCE: Project Leads for MQ EIS/KG BSW

## Part 1: Strategic Text Analysis for Leadership
Analyze the provided JSON data context (`open_issues_snapshot`, `stats`, `recent_activity_summary`). Generate a concise, **in-depth**, strategic text analysis focusing on insights **critical for project leadership decision-making**. Go beyond simple reporting of numbers; provide interpretation and potential implications.

**IMPORTANT STATE INTERPRETATION (APPLY STRICTLY):**
*   **Focus analysis on ACTIVE work:** Issues in `Open`, `Reopened`, and `In Progress` represent the team's direct internal workload and potential internal bottlenecks. Prioritize these in your assessment of risks, workload, and performance.
*   **Acknowledge EXTERNAL dependencies:** Issues in `To be discussed` or `To Verify` (if mentioned in stats/history, not in snapshot) indicate waiting for external input or review. **Crucially, DO NOT interpret `To be discussed` issues as internal team bottlenecks or part of the active workload unless specific issue data (comments/assignments) strongly indicates an internal reason. Frame these *primarily* as awaiting external action.**
*   **Pre-filtered snapshot:** Remember that the `open_issues_snapshot` provided to you **HAS ALREADY BEEN FILTERED**. It **DOES NOT CONTAIN** issues in `Cyclic` or `To Verify` states. Your core analysis of specific issues, workload, and bottlenecks MUST focus ONLY on the states present in the snapshot (`Open`, `Reopened`, `In Progress`, `To be discussed`), applying the rule above for `To be discussed`.
*   **IGNORE 'Cyclic':** The 'Cyclic' state is **IRRELEVANT** and **NOT PRESENT** in the data you are analyzing (`open_issues_snapshot`). **DO NOT** mention or analyze anything related to 'Cyclic' issues.
*   **'To Verify' Handled:** Issues in `To Verify` are **NOT INCLUDED** in the `open_issues_snapshot` for your detailed analysis, but they *are* part of the overall total open count and stale count.

**Analysis Sections (Provide Depth and Interpretation):**
- **Overall Project Pulse & Health:** Assess current state, momentum, and overall health (Red/Amber/Green judgment encouraged). **Explain the reasoning** behind the assessment, focusing on trends in `Open/Reopened/In Progress` states, resolution rates, stale issue impact, C/R ratio, and key risks identified below. Mention if a significant number of issues recently transitioned to `To Verify` or `To be discussed` as a potential handoff point.
- **Key Statistics Summary:** Briefly summarize vital stats, providing **clear definitions and context**:
    - Total Open Issues (Count including `To Verify`, `To be discussed` and ACTIVE states, excluding `Cyclic`/Closed): Use the value provided in `stats['total_open_issues']`.
    - Issues Awaiting External Input (Count of `To be discussed`): **Calculate this count STRICTLY from the `open_issues_snapshot` provided.** *This represents dependency on external factors.*
    - Created / Resolved (Last 24h): Use `stats['created_last_24h']` / `stats['resolved_last_24h']`. **Analyze the implication of this ratio on backlog growth/shrinkage.**
    - Average Age of `Open`/`Reopened`/`In Progress` Issues (Days): Calculate avg age **ONLY for these specific states within the `open_issues_snapshot`.** *Interpret what this age suggests about internal throughput.*
    - Stale Issues (>30d, All Open States including `To Verify`/`To be discussed`): Use `stats['overall_metrics']['stale_30d_count']`. *Highlight the overall risk level from aging issues.*
    **Interpret these numbers:** Focus on the balance between creation/resolution, the age of internally active issues, and the total stale count.
- **Distribution Insights:** Briefly mention key distribution patterns (state, priority) for issues in the `open_issues_snapshot` (`Open`/`Reopened`/`In Progress`/`To be discussed`) ONLY if they reveal significant imbalances or trends requiring attention. **Explain *why* a pattern is significant (e.g., many high-priority items stuck in `To be discussed`?) and suggest potential causes.**
- **Assignee Workload & Performance (GEN-04 - Count Based - Phase 1):** Analyze workload distribution **based on counts of ACTIVE issues** (`Open`/`Reopened`/`In Progress` from the snapshot). Highlight assignees with notably high counts of these active issues. Explicitly mention top 1-2 assignees with the highest ACTIVE issue count. **Instead of saying "overloaded", state observations like "Assignee X currently has the highest number of active issues (Y), which may impact their ability to make progress across all items."** You can *separately* mention assignees with many issues in `To be discussed` state, framing it clearly as "awaiting input on X items". **DO NOT include `To be discussed` counts in the primary active workload count assessment.** (Note: Effort-based analysis will replace this in Phase 2).
- **Recent Activity Trends:** Focus on the *implications* of recent changes. **Identify the 1-3 most significant activities/updates from the last 24 hours (e.g., critical issues created/resolved, key status changes *into/out of* ACTIVE states, changes *into* `To Verify` or `To be discussed`, important assignments). For each, provide context: Issue ID, Summary Snippet, Assignee (if relevant), and **analyze the significance and potential impact of the change** (e.g., 'Status changed to Blocked, potentially impacting feature X', 'Issue moved to To Verify, awaiting customer feedback', 'Assigned to Assignee Y, who has the highest active issue count', 'Newly Created critical issue Z needs immediate analysis').** Look for patterns or lack thereof in recent activity (e.g., many issues started but none finished?).
- **Risk, Bottleneck, & Stale Issue Identification (GEN-03):** Explicitly identify and assess key risks, blockers, or bottlenecks evident in the data, **focusing primarily on ACTIVE issues** (`Open`/`Reopened`/`In Progress` from the snapshot). Analyze stale issues (>30 days open), explicitly mentioning the total count. Highlight the 1-2 MOST critical/oldest stale issues, **especially those in ACTIVE states**, with full context: Issue ID, Summary, Assignee, Status, Age (days open), and **analyze *why* they are a risk (e.g., blocking dependencies, critical feature impact, long stagnation, assigned to person with high active count). Look for common themes or assignees among stale ACTIVE issues.** Similarly, highlight the 1-2 most critical **new** issues or **blockers** (in ACTIVE states), providing the same level of context and risk analysis. Briefly mention if very old `To be discussed` issues exist, framing them as long-pending external dependencies requiring **escalation analysis**.

**Guiding Principles:** Prioritize **actionable, in-depth, analytical insights** for the team's ACTIVE work. Assess strategic impact, risk within ACTIVE issues, and performance overview. **Fulfill GEN-03 and GEN-04 requirements explicitly, focusing on ACTIVE states and providing analysis of causes and impacts, not just reporting.** Be concise but thorough. Interpret the meaning for leadership, **strictly distinguishing between internal team workload/bottlenecks (`Open`/`Reopened`/`In Progress`) and external dependencies (`To be discussed`/`To Verify`) based on issue state.** When highlighting specific issues or activities deemed significant, PROVIDE FULL CONTEXT and DEEP ANALYSIS. Trust your judgment on significance, but ensure referenced items are fully contextualized and analyzed.
Structure the analysis logically with clear markdown headings.

## Part 2: Generate Python Plot Code
Based on the *same* JSON data context, identify and generate Python code using `matplotlib.pyplot` (as `plt`) and `pandas` (as `pd`) for **3 distinct, insightful visualizations** that would be most valuable for a daily project status report.

**Goal:** Generate code for **exactly 3 distinct plots** that provide value for a daily project status report. Choose diverse plot types (e.g., horizontal bar charts, pie charts, potentially time series if data allows) based on what best communicates the insight from the available data. You **must** generate code for 3 plots.

**Data Context Available:**
The code you generate will have access to the following Python variables:
- `assignee_workload_dict`: A dictionary mapping assignee names (str) to open issue counts (int). Example: `{'user1': 5, 'user2': 3}`
 - `state_counts_dict`: A dictionary mapping issue state names (str) to open issue counts (int). Example: `{'Open': 10, 'In Progress': 5, 'To be discussed': 8}`
- `recent_activity_metrics`: A dictionary with keys like 'created', 'resolved', 'new_blockers', 'new_critical' for the last 24h.
- `overall_metrics`: A dictionary potentially containing 'Stale(>30d)' count and the 'Workload Summary' dict.

**Plot Suggestions:** Consider visualizing assignee workload (`assignee_workload_dict`, perhaps filtered for active states if possible in the execution context), issue state distribution (`state_counts_dict` - **clearly separating active vs. waiting states like 'To be discussed'**), and recent activity (`recent_activity_metrics` - e.g., created vs. resolved). Select the 3 most impactful visualizations for the daily report. Ensure plots are clear and provide context (e.g., showing both counts and percentages where appropriate).

**Code Requirements:**
- Import necessary libraries: `import matplotlib.pyplot as plt`, `import pandas as pd`.
- Generate code for **exactly 3 distinct, insightful plots** whenever possible based on the data.
- Prioritize clarity and insightfulness relevant to a daily standup/report.
- **Ensure plots display both counts and percentages where applicable (e.g., on pie slices, bar labels).**
- For each plot:
    - Start with `plt.figure(figsize=(10, 6))` (or similar appropriate size).
    - Add clear titles and axis labels.
    - Use the provided data variables (e.g., `assignee_workload_dict`).
    - **Crucially**: Save the plot using `plt.savefig('./data/plots/plot_N.png')` where N is the plot index (1, 2, or 3). Ensure the directory `./data/plots/` is part of the path.
    - **Crucially**: Close the plot figure using `plt.close()` after saving to free up memory.
- Ensure the generated code is syntactically correct Python.

**Output Format:**
First, provide the full text analysis from Part 1.
Then, **immediately following the analysis text, without any other content**, provide each generated Python plot code block.
**Each code block MUST be strictly enclosed in its own markdown code fences, starting EXACTLY with ```python and ending EXACTLY with ```.**
There must be **NO** text, comments, or data between the closing ``` of one block and the opening ```python of the next.
Do **NOT** include the input JSON data context in your final output.
"""
        prompt += "\nProvide *only* the analysis text and the **correctly fenced** Python code blocks as requested."
        return prompt

    # --- Updated method to generate text analysis AND extract plot code ---
    def _generate_analysis_and_plot_code(self, cleansed_data_context: Dict[str, Any]) -> Tuple[str, List[str]]:
        """
        Generates text analysis and extracts Python plot code snippets using a single API call.
        Expects data context to be pre-cleansed. Does NOT use code execution tool.
        Returns a tuple: (analysis_text: str, plot_code_strings: List[str])
        """
        logger.info("Initiating combined text analysis and plot code generation step...")
        full_response_text = ""
        plot_code_strings = []
        # Use the combined prompt
        prompt = self._create_analysis_and_plot_code_prompt()

        try:
            context_json = json.dumps(cleansed_data_context, indent=2, ensure_ascii=False) # Use ensure_ascii=False for potentially non-ASCII names
            prompt_parts = [prompt, "\\n\\n--- Data Context (JSON) ---\\n", context_json]
            logger.debug("Sending request to Gemini for combined analysis and plot code...")

            # Configure Generation (No tools needed)
            generation_config_obj = types.GenerationConfig(**self.generation_config_dict)

            # Make the API call
            response = self.model.generate_content(
                prompt_parts,
                generation_config=generation_config_obj
                # No tools argument needed
            )
            logger.debug("Received response from Gemini for combined step.")
            # logger.debug(f"Raw combined response object: {response}") # Keep commented unless needed

            # Process response parts (expecting only text)
            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.text:
                        full_response_text += part.text
                    else:
                         logger.warning(f"Received unexpected non-text part in combined response: {part}")

            if not full_response_text:
                logger.warning("No text content extracted from the Gemini response for combined analysis/code.")
                return "", [] # Return empty analysis and no code
            else:
                # --- EXTRACT FIRST, THEN CLEAN --- 
                # 1. Extract all fenced Python code blocks from the entire response
                plot_code_strings = re.findall(r"```python\s*([\s\S]+?)\s*```", full_response_text)
                logger.info(f"Extracted {len(plot_code_strings)} plot code blocks from the full response.")

                # 2. Create clean analysis text by removing everything FROM the first code block onwards
                code_start_marker = "```python"
                code_start_index = full_response_text.find(code_start_marker)
                
                if code_start_index != -1:
                    # If marker is found, take text only *before* it
                    clean_analysis_text = full_response_text[:code_start_index].strip()
                    logger.info(f"Cleaned analysis text by slicing before first '{code_start_marker}'.")
                else:
                    # If marker is not found, assume the whole response is analysis (shouldn't happen if plots are expected)
                    clean_analysis_text = full_response_text.strip()
                    logger.warning(f"Code start marker '{code_start_marker}' not found. Using full response as analysis.")

                # Optional: Add a log to check the cleaned text
                # logger.info(f"--- Cleaned Analysis Text --- \n{clean_analysis_text[:500]}...\n---")

                # 3. Return the clean analysis and the code strings
                return clean_analysis_text, plot_code_strings

        except Exception as e:
            logger.error(f"Error during combined analysis/plot code generation: {e}", exc_info=True)
            # Return error message in text, empty list for code
            return f"Error generating AI analysis and plot code: {str(e)}", []

    # --- DELETE _generate_plots, _create_plot_generation_prompt, _save_plot_image ---
    # --- Method deletion happens implicitly by not including them ---

    # --- Text Analysis Prompt --- 
    def _create_text_analysis_prompt(self) -> str:
        """Creates the prompt for generating the main text analysis ONLY."""
        # This prompt assumes plots are generated separately.
        prompt = """
# TASK: Text Analysis
Analyze the provided JSON data context and generate a comprehensive text analysis covering:
- Overall project pulse and health assessment.
- Key statistics summary (total open, created/resolved recently, average age, stale count).
- Distribution insights (issues by state, priority, type).
- Assignee workload analysis (highlighting overloaded or idle assignees, unassigned count).
- Recent activity trends (types of changes, velocity indicators).
- Potential risks, blockers, or bottlenecks identified from the data.
- Stale issue analysis (>30 days).

Focus the analysis *only* on the provided data context. Structure the analysis logically with clear headings or sections (using markdown if helpful).
"""
        return prompt

    # --- Refocused Step 1 method to ONLY do text analysis ---
    def _generate_text_analysis(self, cleansed_data_context: Dict[str, Any]) -> str:
        """
        Generates the main text analysis using a dedicated API call.
        Expects data context to be pre-cleansed.
        Does NOT use code execution.
        """
        logger.info("Initiating text analysis step...")
        raw_analysis_text = ""
        prompt = self._create_text_analysis_prompt() # Use the text-focused prompt

        try:
            context_json = json.dumps(cleansed_data_context, indent=2)
            prompt_parts = [prompt, "\n\n--- Data Context ---\n", context_json]
            logger.debug("Sending request to Gemini for text analysis...")

            # Configure Generation (No tools needed)
            generation_config_obj = types.GenerationConfig(**self.generation_config_dict)

            # Make the API call
            response = self.model.generate_content(
                prompt_parts,
                generation_config=generation_config_obj
                # No tools argument needed
            )
            logger.debug("Received response from Gemini for text analysis step.")

            # Process response parts (expecting only text)
            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.text:
                        raw_analysis_text += part.text
                    else:
                         logger.warning(f"Received unexpected non-text part in text analysis response: {part}")
            elif not response.candidates:
                 logger.warning("Text analysis response had no candidates.")
                 if hasattr(response, 'prompt_feedback'): logger.warning(f"Text Analysis Prompt Feedback: {response.prompt_feedback}")

            # This section needs to be OUTSIDE the try block
            if not raw_analysis_text:
                    logger.warning("No raw analysis text was extracted from the Gemini response.")
                    # Log feedback/reason
                    try:
                        if hasattr(response, 'prompt_feedback'): logger.warning(f"Text Analysis Prompt Feedback: {response.prompt_feedback}")
                        if response.candidates and hasattr(response.candidates[0], 'finish_reason'): logger.warning(f"Text Analysis Finish Reason: {response.candidates[0].finish_reason}")
                    except Exception as log_err:
                        logger.error(f"Error accessing text analysis response feedback/reason: {log_err}")

        # Correctly indented except block
        except Exception as e:
            logger.error(f"Error during text analysis generation: {e}", exc_info=True)
            # Return empty string or error indicator on failure?
            raw_analysis_text = f"Error generating text analysis: {str(e)}"

        logger.info(f"Finished text analysis step. Analysis length: {len(raw_analysis_text)}")
        return raw_analysis_text

    # --- DELETE STRUCTURED SUMMARY PROMPT --- 
    # def _create_structured_summary_prompt(self) -> str:
    #    ... (method deleted) ...

    # --- Orchestration Method --- 
    def generate_leadership_report_insights(self, data_processor) -> Dict[str, Any]:
        """
        Main pipeline for generating AI insights.
        Generates text analysis, plot code suggestions, and voice script directly from analysis.
        Does NOT generate a separate structured summary anymore.
        """
        logger.info("Starting AI insight generation pipeline (No Structuring Step)...")
        final_results = {
            "analysis_text": "", # Changed: This will be the main report body now
            # "structured_summary": {}, # REMOVED
            "voice_script": "",
            "plot_code_strings": [],
            "plot_filenames": [],
            "error": None
        }

        try:
            # 1. Prepare Data Contexts
            logger.info("Preparing data context for analysis and plot code...")
            full_data_context = self._prepare_data_context(data_processor)
            cleansed_full_context = self._cleanse_before_json(full_data_context)

            # 2. Generate Text Analysis AND Plot Code (Combined Call)
            analysis_text, plot_code_strings = self._generate_analysis_and_plot_code(cleansed_full_context)
            final_results["analysis_text"] = analysis_text
            final_results["plot_code_strings"] = plot_code_strings

            if not analysis_text or analysis_text.startswith("Error generating AI analysis"):
                 final_results["error"] = f"Failed during AI analysis/code generation: {analysis_text or 'No text returned'}"
                 logger.error(final_results["error"])
                 return final_results # Stop early if core analysis failed

            # --- ADDED: Step 2.5 Generate Turkish Translation --- 
            logger.info("Generating Turkish translation...")
            turkish_analysis = self._generate_turkish_analysis(analysis_text)
            final_results["turkish_analysis"] = turkish_analysis
            if turkish_analysis.startswith("Hata:") or turkish_analysis.startswith("Çeviri Hatası:"):
                # Log the translation error but don't stop the pipeline
                logger.error(f"Turkish translation failed: {turkish_analysis}")
                # Optionally add to main error string
                final_results["error"] = (final_results.get("error","") + "; " if final_results.get("error") else "") + "Turkish translation failed."
            # --- END ADDED --- 

            # --- STEP 3 REMOVED (Structured Summary Generation) ---

            # 4. Generate Voice Script (using the RAW analysis text)
            logger.info("Generating voice script from raw analysis...")
            # CORRECTED CALL: Pass the actual analysis_text obtained from the combined call
            voice_script = self._generate_voice_script(analysis_text)
            if "Error:" in voice_script:
                 final_results["error"] = (final_results.get("error","") + "; " if final_results.get("error") else "") + voice_script
                 logger.error(f"Failed during voice script generation: {voice_script}")
            final_results["voice_script"] = voice_script

        except Exception as e:
            logger.error(f"AI insight generation pipeline failed: {e}", exc_info=True)
            final_results["error"] = f"Pipeline Error: {str(e)}"
            return final_results

        logger.info("AI insight generation pipeline finished (No Structuring Step).")
        return final_results

    def generate_daily_report(self, data_processor) -> Dict[str, Any]:
        """
        DEPRECATED: Use generate_leadership_email_content instead.
        Generate a daily insight report.

        Args:
            data_processor: DataProcessor instance with loaded data

        Returns:
            Dictionary with sections of insights
        """
        logger.warning("generate_daily_report is deprecated. Use generate_leadership_email_content.")
        # Redirect to the new method for now, but ideally update callers
        return self.generate_leadership_email_content(data_processor)


    # --- NEW LEADERSHIP REPORT METHODS ---

    def _get_leadership_email_prompt(self) -> str:
        """Returns the system prompt for the detailed leadership email report."""
        return """
# MISSION: Deliver mission-critical intelligence to Mercedes project leadership for the "MQ EIS/KG BSW" project, transforming YouTrack data into decisive daily action items.

# ROLE: Expert Project Analyst & AI Assistant for Mercedes "MQ EIS/KG BSW" Leadership

# TASK: Analyze the provided YouTrack data context and generate a structured, actionable DAILY email report adhering strictly to the specified format and principles.

# PROJECT CONTEXT: Mercedes "MQ EIS/KG BSW"

# DATA CONTEXT:
# - `project_stats`: Overall counts, recent activity (weekly/monthly created/resolved), resolution times, backlog changes, velocity metrics.
# - `status_distribution`, `priority_distribution`, `issue_type_distribution`: Current issue breakdowns.
# - `assignee_workload`: Open issues per assignee (use if available, state if not).
# - `sprint_statistics`: Info on current/past sprints (use if available).
# - `recent_issue_samples`, `open_issue_samples`, `stale_issue_samples`: Examples of issues (use `readable_id`, `summary`, `assignee`, `priority`, `state`, `created`, `days_open`).
# - `closed_issues_summary`: Historical trends for context (resolution stats, monthly counts).
# - `recent_activity`: Log of recent changes (last 7 days).
# - **Potential Limitations:** Acknowledge if key metrics (e.g., workload, resolution time, velocity) cannot be calculated accurately due to missing fields noted in logs or context. State this clearly where relevant.

# IMPLEMENTATION PRINCIPLES (Adhere Strictly):
# 1. **Ruthless Relevance:** Every insight MUST inform a potential decision. Filter noise. Prioritize anomalies, exceptions, and changes.
# 2. **Contextual Intelligence:** Connect insights to project milestones/goals (implicitly, based on MQ EIS/KG BSW context). Reference historical patterns if clear in data.
# 3. **Actionable Precision:** Provide specific, concrete next steps. Include direct links/references (e.g., `readable_id`). Quantify impact/urgency.
# 4. **Leadership Perspective:** Focus on strategic implications, cross-team impacts, business objectives.

# OUTPUT STRUCTURE (Use Markdown - Follow EXACTLY):

## DAILY PROJECT PULSE
*   **Project Health:** [RED/AMBER/GREEN based on overall status, blockers, trends - make a judgment call] | Day-over-Day Change: [Brief note on change, e.g., "Stable", "Increased Risk", "Improved Velocity"]
*   **Critical Metrics:** Open: `project_stats['open_issues']` | Blockers: [Count if identifiable, otherwise state N/A] | SLA Breaches: [Count if identifiable, otherwise state N/A] | Velocity Trend: [`project_stats['avg_issues_resolved_per_week']` if available, mention trend up/down/stable]
*   **Today's Focus (Top 3):**
    1.  [Highest priority item requiring leadership attention, e.g., Critical stale issue, resource conflict, major blocker - cite `readable_id`]
    2.  [Second priority item]
    3.  [Third priority item]

## RISK INTELLIGENCE
*   **New Blockers:** [List any newly identified blockers from `recent_activity` or high-priority `open_issue_samples` with state 'Blocked'. State "None identified" if applicable.] | Impact: [Brief assessment] | Recommended Action: [Specific suggestion]
*   **Approaching Deadlines / Stale Issues:** [Highlight issues nearing deadlines (if data available) OR list top 1-2 `stale_issue_samples` (>30 days open)] | Probability/Risk: [Brief assessment] | Action: [Suggestion]
*   **Resource Conflicts/Bottlenecks:** [Identify potential conflicts based on `assignee_workload` (e.g., high load on key person) OR bottlenecks based on slow-moving states. State "None apparent" if not clear from data.] | Impact: [Brief assessment]
*   **Emerging Patterns:** [Identify any concerning patterns, e.g., increase in specific `issue_type_distribution`, recurring blockers in `recent_activity`. State "No significant new patterns" if applicable.]

## TEAM PERFORMANCE
*   **Workload Distribution:** [Summarize `assignee_workload`. Highlight top 1-2 overloaded members (> avg issues). State "Assignee workload data unavailable" if context is empty/missing.] | Recommendation: [Suggest rebalancing or support if applicable.]
*   **Velocity & Throughput:** Weekly Resolved: [`project_stats['avg_issues_resolved_per_week']` if available] | Trend: [Up/Down/Stable based on recent vs. historical] | Blocked Members: [Identify assignees with multiple 'Blocked' status issues if possible. State "None identified" otherwise.]
*   **Capacity Forecast:** [Brief comment on team's capacity based on current open issues vs. velocity. E.g., "Backlog growing", "Capacity strained", "Velocity matches creation rate". Requires `avg_issues_per_week` and `avg_issues_resolved_per_week`.]

## 24-HOUR ACTIVITY SUMMARY
*   **Key Status Changes:** [List 1-3 significant status changes from `recent_activity` (e.g., issue moved to 'Blocked', 'Resolved', 'In Progress'). Cite `readable_id`.]
*   **Notable Comments/Updates:** [Highlight 1-2 key comments or updates from `recent_activity` if identifiable (e.g., comments added to high-priority issues). State "No major comments noted" otherwise.]
*   **New Issues:** [Mention count of `project_stats['recently_created']` (adjust if timeframe differs). Highlight 1-2 critical new issues if any in `recent_issue_samples`.] | Impact Assessment: [Briefly assess impact of new critical issues.]
*   **Recently Resolved:** [Mention count of `project_stats['recently_resolved']`. Highlight 1-2 significant resolutions if any.] | Verification Needs: [Note if any resolved issues need specific verification.]

# FINAL CHECK: Ensure every section is populated according to the structure. If data is missing for a point, explicitly state "Data unavailable" or "N/A". Be concise and action-oriented.
"""

    def _get_voice_summary_prompt(self) -> str:
        """Returns the system prompt for the concise voice summary script."""
        return """
# MISSION: Generate a concise, ~2-minute audio script summarizing the most critical daily intelligence for Mercedes "MQ EIS/KG BSW" project leadership.

# ROLE: AI Project Briefing Assistant

# TASK: Analyze the provided YouTrack data context and generate a script optimized for audio delivery via ElevenLabs, focusing ONLY on the absolute highest priorities.

# PROJECT CONTEXT: Mercedes "MQ EIS/KG BSW"

# DATA CONTEXT: (Same as email report, focus on extracting the most critical points)
# - `project_stats`: Key numbers (open, resolved, recent changes).
# - `open_issue_samples`, `stale_issue_samples`: For identifying critical blockers/stale items.
# - `assignee_workload`: For identifying major workload imbalances.
# - `recent_activity`: For identifying critical new blockers or status changes.

# SCRIPT CHARACTERISTICS (Adhere Strictly):
# - **Conciseness:** Target 150-170 words per minute (~300-340 words total). Ruthlessly prioritize.
# - **Structure:**
#   1. **Opening:** "Good morning. Here is your MQ EIS/KG BSW daily briefing for [Date]." State overall health (Red/Amber/Green - use judgment) and key numbers (Open issues, Blockers).
#   2. **Today's Top 3 Focus Items:** Clearly state the 3 most critical items (e.g., critical blocker `readable_id`, urgent stale issue, major resource conflict). Briefly state the impact.
#   3. **Team Performance Highlight:** Mention ONE key performance point (e.g., significant velocity change, major workload imbalance).
#   4. **Closing Action:** State ONE key recommended leadership action for the day. "Recommendation: [Action]".
# - **Audio Optimization:** Use clear, direct language. Spell out issue IDs like "E. I. S. M. M. A. B. S. W. dash one two three". Use pauses (...) strategically between sections. Emphasize numbers and actions. Avoid complex sentences.
# - **Content Focus:** Only include information requiring immediate leadership attention or action. Omit routine updates.

# OUTPUT FORMAT:
# - Plain text script.
# - Include strategic pauses indicated by (...).
# - NO Markdown formatting.
# - NO introductory or concluding text beyond the specified structure.

# EXAMPLE (Style guide, content will vary):
# Good morning. Here is your MQ EIS/KG BSW daily briefing for 2025-04-03.
# Project health is Amber. Currently 58 open issues, 3 critical blockers.
# (...)
# Today's focus items are:
# First, Blocker E. I. S. M. M. A. B. S. W. dash one six nine one requires immediate dependency resolution.
# Second, Stale issue E. I. S. M. M. A. B. S. W. dash one five zero zero is impacting the critical path.
# Third, Assignee John Doe is significantly overallocated with 15 open issues.
# (...)
# Team velocity has decreased by 10 percent this past week.
# (...)
# Recommendation: Prioritize unblocking issue E. I. S. M. M. A. B. S. W. dash one six nine one today.

# GENERATE THE VOICE SCRIPT BASED ON THE PROVIDED DATA CONTEXT.
"""

    def generate_leadership_email_content(self, data_processor) -> Dict[str, Any]:
        """
        Generates the structured content for the leadership email report.

        Args:
            data_processor: DataProcessor instance with loaded data

        Returns:
            Dictionary with keys matching the email sections:
            'daily_pulse', 'risk_intelligence', 'team_performance', 'activity_summary', 'error' (optional)
        """
        logger.info("Generating leadership email content")

        if not API_KEY_VALID:
            logger.warning("Invalid or missing Gemini API key - returning standard message")
            return {
                "daily_pulse": "AI insights unavailable - Gemini API key is missing or invalid.",
                "risk_intelligence": "AI analysis requires a valid API key.",
                "team_performance": "AI analysis requires a valid API key.",
                "activity_summary": "AI analysis requires a valid API key.",
                "error": "Missing or invalid Gemini API key."
            }

        try:
            context = self._prepare_data_context(data_processor)
            closed_issues_summary = self._summarize_closed_issues(data_processor)
            context["closed_issues_summary"] = closed_issues_summary

            system_prompt = self._get_leadership_email_prompt()

            def json_serial(obj):
                if isinstance(obj, (np.integer, np.int64)): return int(obj)
                if isinstance(obj, (np.floating, np.float64)): return float(obj)
                if isinstance(obj, np.bool_): return bool(obj)
                if isinstance(obj, np.ndarray): return obj.tolist()
                if isinstance(obj, (pd.Timestamp, datetime)): return obj.isoformat()
                raise TypeError(f"Type {type(obj)} not serializable")

            context_copy = self._cleanse_before_json(context)
            user_prompt = f"""
            Analyze the following YouTrack data context for the MQ EIS/KG BSW project (as of {datetime.now().strftime('%Y-%m-%d')}) and generate the report according to the system prompt's structure and principles:

            {json.dumps(context_copy, indent=2, default=json_serial)}
            """

            # Log context for debugging
            try:
                json_data = json.dumps(context_copy, default=json_serial)
                logger.info(f"Sending context to Gemini API for email report with {len(json_data)} characters")
                # Optional: Save context to file if needed
                # with open("debug_gemini_email_context.json", "w") as f: f.write(json_data)
            except Exception as e:
                logger.error(f"Error serializing context for email logging: {str(e)}")

            response = self.model.generate_content(
                [system_prompt, user_prompt],
                generation_config={
                    "temperature": 0.2, "top_p": 0.95, "top_k": 40, "max_output_tokens": 4096
                }
            )
            raw_insights = response.text
            logger.debug(f"Raw AI response for email: {raw_insights}")

            # --- Parse the response into the structured dictionary ---
            parsed_content = {
                "daily_pulse": "Data unavailable or parsing failed.",
                "risk_intelligence": "Data unavailable or parsing failed.",
                "team_performance": "Data unavailable or parsing failed.",
                "activity_summary": "Data unavailable or parsing failed."
            }
            current_section_key = None
            section_headers = {
                "DAILY PROJECT PULSE": "daily_pulse",
                "RISK INTELLIGENCE": "risk_intelligence",
                "TEAM PERFORMANCE": "team_performance",
                "24-HOUR ACTIVITY SUMMARY": "activity_summary"
            }

            for line in raw_insights.splitlines():
                stripped_line = line.strip().upper().replace("## ", "").replace("# ", "")
                # Check if line is a section header
                is_header = False
                for header, key in section_headers.items():
                    if stripped_line == header:
                        current_section_key = key
                        parsed_content[current_section_key] = "" # Initialize section
                        is_header = True
                        break
                # If it's not a header and we are inside a section, append the line
                if not is_header and current_section_key:
                    # Append line, preserving original formatting (like bullet points)
                    if parsed_content[current_section_key] == "":
                         parsed_content[current_section_key] += line.strip() # First line
                    else:
                         parsed_content[current_section_key] += "\n" + line.strip() # Subsequent lines

            # Clean up leading/trailing whitespace in each section
            for key in parsed_content:
                parsed_content[key] = parsed_content[key].strip()
                # If a section remained empty after parsing, use default message
                if not parsed_content[key]:
                     parsed_content[key] = "Data unavailable or parsing failed for this section."


            logger.info("Successfully generated and parsed leadership email content.")
            return parsed_content

        except Exception as e:
            logger.error(f"Error generating leadership email content: {str(e)}", exc_info=True)
            error_message = str(e)
            if "429" in error_message and "quota" in error_message:
                logger.warning("Gemini API rate limit exceeded for email report")
                return {
                    "daily_pulse": "Rate limit exceeded.", "risk_intelligence": "Rate limit exceeded.",
                    "team_performance": "Rate limit exceeded.", "activity_summary": "Rate limit exceeded.",
                    "error": "Gemini API rate limit exceeded."
                }
            else:
                return {
                    "error": f"Failed to generate email content: {str(e)}",
                    "daily_pulse": f"Error: {str(e)}", "risk_intelligence": f"Error: {str(e)}",
                    "team_performance": f"Error: {str(e)}", "activity_summary": f"Error: {str(e)}"
                }

   

    # --- VOICE SCRIPT PROMPT (MODIFIED FOR RAW TEXT INPUT) ---
    def _create_voice_script_prompt(self) -> str:
        """Returns the system prompt for the voice summary script (based on raw analysis)."""
        return """
# MISSION: Generate a comprehensive audio script summarizing the key findings from the daily raw text analysis for Mercedes "MQ EIS/KG BSW" project leadership.

# ROLE: AI Project Briefing Assistant

# TASK: Analyze the provided raw text analysis and generate a script suitable for audio delivery via ElevenLabs. Summarize the main sections or themes present in the text.

# PROJECT CONTEXT: Mercedes "MQ EIS/KG BSW"

# DATA CONTEXT: Raw, freeform text analysis derived from YouTrack data.

# SCRIPT CHARACTERISTICS:
# - **Comprehensive Summary:** Extract and summarize the main points discussed in the raw analysis (e.g., overall health, key risks/stale issues mentioned, workload concerns, significant recent activities).
# - **Structure (Flexible):**
#   1. **Opening:** "Good morning. Here is your MQ EIS/KG BSW daily briefing for [Date]."
#   2. **Key Insights:** Summarize the 2-4 most important findings or themes from the raw text analysis.
#   3. **Specific Callouts:** If the analysis highlighted specific critical issues (e.g., EISMMABSW-XXX), mention 1-2 of the most important ones briefly.
#   4. **Closing:** (Optional - can be omitted or a simple sign-off)
# - **Audio Optimization:** Use clear, direct language. Spell out issue IDs like "E. I. S. M. M. A. B. S. W. dash one two three". Use pauses (...) strategically. Emphasize key findings.
# - **Flexibility:** Adapt the length based on the significance and length of the input text. Aim for clarity and completeness over strict brevity.

# OUTPUT FORMAT:
# - Plain text script.
# - Include strategic pauses indicated by (...).
# - NO Markdown formatting.
# - NO introductory or concluding text beyond the specified structure.

# GENERATE THE VOICE SCRIPT BASED ON THE PROVIDED RAW ANALYSIS TEXT.
"""

    # --- VOICE SCRIPT GENERATION (MODIFIED FOR RAW TEXT INPUT) ---
    def _generate_voice_script(self, raw_analysis_text: str) -> str:
        """
        Generates the voice script directly from the raw analysis text.

        Args:
            raw_analysis_text: The raw analysis text string.

        Returns:
            String containing the voice script, or an error message.
        """
        logger.info("Initiating voice script generation from raw analysis text...")
        if not raw_analysis_text or raw_analysis_text.startswith("Error generating AI analysis"):
            logger.warning("Cannot generate voice script: Raw analysis input is empty or contains an error.")
            return "Error: Could not generate voice summary due to issues in the analysis phase."

        # Assemble input for the prompt
        # Add date context if needed - Assuming date is available elsewhere or not critical for this prompt
        input_text_for_voice = raw_analysis_text 

        system_prompt = self._create_voice_script_prompt() # Use the updated prompt method
        user_prompt = f"Here is the raw analysis text:\n\n```text\n{input_text_for_voice}\n```\n\nNow, please generate the conversational voice script summarizing this text, following the system prompt instructions precisely."
        
        try:
            # Use a config suitable for summarization/creative text, adjust token limit for potentially longer input
            voice_config = self.generation_config_dict.copy()
            voice_config['temperature'] = 0.7 # Slightly more creative for script
            voice_config['max_output_tokens'] = 1024 # Might need adjustment based on raw text length

            config = types.GenerationConfig(**voice_config)
            response = self.model.generate_content(
                 [system_prompt, user_prompt],
                 generation_config=config
            )

            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                script_text = "".join(part.text for part in response.candidates[0].content.parts if part.text).strip()
                logger.info("Voice script generated successfully from raw analysis.")
                
                # Clean up common markdown artifacts just in case
                script_text = script_text.replace('**', '').replace('* ', '')
                # Replace issue IDs for better pronunciation
                script_text = re.sub(r'(EISMMABSW-)(\d+)', r'E. I. S. M. M. A. B. S. W. dash \\2', script_text)
                
                return script_text
            else:
                logger.warning("Voice script generation failed: No content in response.")
                return "Error: Failed to generate voice script content."
        except Exception as e:
            logger.error(f"Error generating voice script from raw analysis: {e}", exc_info=True)
            return f"Error generating voice script: {str(e)}"

    # <<< NEW: Function for Turkish Translation >>>
    def _generate_turkish_analysis(self, english_analysis_text: str) -> str:
        """
        Translates the English analysis text to Turkish using the Gemini API.
        Also removes erroneous markdown code fences if the AI adds them.

        Args:
            english_analysis_text: The generated English analysis text.

        Returns:
            The translated Turkish text, or an error message.
        """
        logger.info("Initiating Turkish translation of the analysis text...")
        if not english_analysis_text or english_analysis_text.startswith("Error generating"):
            logger.warning("Cannot translate: Input English analysis is missing or contains an error.")
            return "Hata: İngilizce analiz metni eksik veya hatalı olduğu için çeviri yapılamadı."

        # <<< MODIFIED SYSTEM PROMPT FOR TRANSLATION >>>
        system_prompt = "You are a highly proficient technical translator specializing in software project management reports. Your task is to accurately translate the provided English text into professional, natural-sounding Turkish. Maintain the original meaning, tone, and markdown formatting (like headers and bullet points). **IMPORTANT: Do NOT translate YouTrack issue IDs (e.g., EISMMABSW-1234) and do NOT translate the English issue summary text that typically follows the ID (often enclosed in quotes or starting after a colon). Keep the issue IDs and their English summaries exactly as they appear in the original English text.**"
        user_prompt = f"Please translate the following English project analysis report into Turkish, following all instructions in the system prompt (especially regarding not translating issue IDs and summaries):\n\n```markdown\n{english_analysis_text}\n```"

        try:
            # Use generation config suitable for translation (low temperature)
            translate_config = self.generation_config_dict.copy()
            translate_config['temperature'] = 0.1
            translate_config['max_output_tokens'] = 4096 # Allow sufficient tokens for translation

            config = types.GenerationConfig(**translate_config)
            response = self.model.generate_content(
                 [system_prompt, user_prompt],
                 generation_config=config
            )

            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                turkish_text = "".join(part.text for part in response.candidates[0].content.parts if part.text).strip()
                
                # Clean potential erroneous code fences
                cleaned_turkish_text = re.sub(r"^```markdown\s*|\s*```$", "", turkish_text, flags=re.MULTILINE | re.DOTALL).strip()
                
                if len(cleaned_turkish_text) < len(turkish_text): # Log if cleaning occurred
                    logger.info("Removed markdown code fences wrapped around the Turkish translation.")
                
                logger.info("Turkish translation generated and cleaned successfully.")
                return cleaned_turkish_text # Return the cleaned version
            else:
                logger.warning("Turkish translation failed: No content in response.")
                return "Hata: Çeviri sırasında modelden içerik alınamadı."
        except Exception as e:
            logger.error(f"Error generating Turkish translation: {e}", exc_info=True)
            return f"Çeviri Hatası: {str(e)}"
    # <<< END NEW FUNCTION >>>

    def analyze_issue_trends(self, data_processor) -> Dict[str, Any]:
        """
        Analyze issue trends over time.

        Args:
            data_processor: DataProcessor instance with loaded data

        Returns:
            Dictionary with trend analysis
        """
        logger.info("Analyzing issue trends with AI")

        # Check if API key is valid and properly configured
        if not API_KEY_VALID:
            logger.warning("Invalid or missing Gemini API key - returning standard message")
            return {
                "error": "AI-based trend analysis unavailable - Gemini API key is missing or invalid.",
                "trend_data": [],
                "analysis": "To enable AI-powered trend analysis, please provide a valid Google Gemini API key."
            }

        try:
            # Prepare time-series data
            if data_processor.issues_df is None or data_processor.issues_df.empty:
                return {"error": "No issue data available for trend analysis"}

            # Create weekly issue data
            issues_df = data_processor.issues_df.copy()
            issues_df['created_week'] = issues_df['created'].dt.to_period('W').dt.start_time
            weekly_created = issues_df.groupby('created_week').size().reset_index()
            weekly_created.columns = ['week', 'created_count']

            # Calculate weekly resolved
            resolved_df = issues_df.dropna(subset=['resolved']).copy()
            if not resolved_df.empty:
                resolved_df['resolved_week'] = resolved_df['resolved'].dt.to_period('W').dt.start_time
                weekly_resolved = resolved_df.groupby('resolved_week').size().reset_index()
                weekly_resolved.columns = ['week', 'resolved_count']

                # Merge created and resolved
                weekly_data = weekly_created.merge(weekly_resolved, left_on='week', right_on='week', how='outer').fillna(0)
                weekly_data = weekly_data.sort_values('week')

                # Convert to records
                trend_data = weekly_data.to_dict(orient='records')
            else:
                trend_data = weekly_created.to_dict(orient='records')

            # Convert data for serialization using our centralized helper method
            trend_data_converted = self._cleanse_before_json(trend_data)

            # Create prompt with JSON serialization
            def json_serial(obj):
                """JSON serializer for objects not serializable by default json code"""
                if isinstance(obj, (pd.Timestamp, datetime)):
                    return obj.isoformat()
                return str(obj)

            prompt = f"""
# ROLE: Trend Analyst for Mercedes "MQ EIS/KG BSW" Project

# TASK: Analyze weekly YouTrack issue creation/resolution trends.

# PROJECT CONTEXT: Mercedes "MQ EIS/KG BSW"

# DATA PROVIDED:
# - `trend_data`: A list of weekly records with `week` (start date), `created_count`, and `resolved_count` (optional).

# ANALYSIS FOCUS:
# - Identify significant shifts in issue creation rates.
# - Analyze resolution trends and team velocity (resolved_count per week).
# - Detect periods of backlog growth (created > resolved) or reduction.
# - Highlight any anomalies or weeks with unusual activity.
# - Briefly forecast near-term trends if patterns are clear.
# - Provide actionable recommendations related *specifically* to improving throughput/velocity.

# OUTPUT STRUCTURE (Use Markdown):

## 1. Overall Trend Analysis
   - Describe the general pattern of issue creation and resolution over the period.

## 2. Key Observations & Anomalies
   - List 2-3 specific observations (e.g., a spike in creation, a drop in resolution) with corresponding weeks.

## 3. Velocity & Backlog Assessment
   - Discuss the trend in weekly resolution count (velocity) and its impact on the backlog.

## 4. Potential Future Trends (Brief)
   - Based *only* on the provided data, suggest if the current trend is likely to continue.

## 5. Recommendations for Velocity
   - Provide 2-3 concrete suggestions to improve issue throughput based on the observed trends.

# STYLE:
# - Concise, data-driven, focused on trends and velocity.
# - Reference specific weeks or counts from the data.
# - If `resolved_count` is missing or consistently zero, state that velocity cannot be accurately assessed.

# DATA:
{json.dumps(trend_data_converted, indent=2, default=json_serial)}

# PROVIDE ANALYSIS BASED ON THE STRUCTURE ABOVE.
            """

            # Generate analysis
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 2048,
                }
            )

            logger.info("Successfully generated trend analysis")
            return {
                "trend_data": trend_data,
                "analysis": response.text
            }

        except Exception as e:
            logger.error(f"Error analyzing issue trends: {str(e)}", exc_info=True)

            # Check for rate limit errors
            error_message = str(e)
            if "429" in error_message and ("rate limit" in str(e).lower() or "quota" in str(e).lower()):
                logger.warning("Gemini API rate limit exceeded for trend analysis")

                # Simply return an empty array - no need to check for trend_data
                trend_data_to_return = []

                return {
                    "error": "API rate limit exceeded. Please try again later.",
                    "trend_data": trend_data_to_return
                }
            else:
                return {
                    "error": f"Failed to analyze trends: {str(e)}"
                }

    def generate_followup_questions(self, data_processor) -> List[str]:
        """
        Generate follow-up questions for project managers based on data analysis.

        Args:
            data_processor: DataProcessor instance with loaded data

        Returns:
            List of follow-up questions
        """
        logger.info("Generating follow-up questions with AI")

        # Check if API key is valid and properly configured
        if not API_KEY_VALID:
            logger.warning("Invalid or missing Gemini API key - returning standard message")
            return [
                "1. AI-powered question generation unavailable - Gemini API key is missing or invalid.",
                "2. Are any issues at risk of missing their deadlines?",
                "3. How is team workload distributed among team members?",
                "4. What was our sprint velocity in the last completed sprint?",
                "5. Are there any recurring issue types that could indicate systemic problems?"
            ]

        try:
            # Prepare context
            context = self._prepare_data_context(data_processor)

            # Convert context for serialization
            context_copy = self._cleanse_before_json(context)

            # Handle any remaining non-serializable types
            def json_serial(obj):
                """JSON serializer for objects not serializable by default json code"""
                if isinstance(obj, (pd.Timestamp, datetime)):
                    return obj.isoformat()
                return str(obj)

            prompt = f"""
# ROLE: Project Assistant for Mercedes "MQ EIS/KG BSW" Team Lead

# TASK: Generate 5 probing follow-up questions based on the provided YouTrack data summary.

# PROJECT CONTEXT: Mercedes "MQ EIS/KG BSW"

# DATA PROVIDED:
# - `project_stats`: Overall counts, recent activity, resolution times.
# - `status_distribution`: Current breakdown of issues by status.
# - `priority_distribution`: Breakdown by priority.
# - `issue_type_distribution`: Breakdown by type.
# - `assignee_workload`: Open issues per assignee (if available).
# - `sprint_statistics`: Info on current/past sprints (if available).
# - `recent_issue_samples`, `open_issue_samples`, `stale_issue_samples`: Examples of issues.
# - `closed_issues_summary`: Historical trends and stats.

# QUESTION FOCUS:
# - Target areas highlighted by the data (e.g., high stale count, low resolution rate, workload imbalance).
# - Encourage deeper investigation into potential risks or bottlenecks.
# - Prompt for specific actions or decisions needed.
# - Be relevant to the daily stand-up or team check-in context.

# OUTPUT FORMAT:
# - Return EXACTLY 5 questions, numbered 1 to 5.
# - Each question should be concise and directly related to the data provided.
# - NO introductory text, NO concluding text, JUST the numbered list.

# EXAMPLE QUESTIONS (Style guide, don't repeat):
# 1. Given the [X] stale issues, which specific ones require immediate attention this week?
# 2. The average resolution time is [Y] days; what are the main blockers affecting this?
# 3. [Assignee Name] has [Z] open issues; do they need support or reprioritization?
# 4. What steps can we take to address the backlog increase of [W] issues last month?
# 5. Based on the low completion rate of the last sprint, what adjustments are needed for the current one?

# DATA:
{json.dumps(context_copy, indent=2, default=json_serial)}

# GENERATE 5 QUESTIONS BASED ON THE FOCUS AND FORMAT ABOVE.
            """

            # Generate questions
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.3,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 1024,
                }
            )

            # Parse the questions
            questions = []
            for line in response.text.split('\n'):
                if line.strip() and (line.strip()[0].isdigit() or line.strip()[0] == '#'):
                    questions.append(line.strip())

            logger.info(f"Generated {len(questions)} follow-up questions")
            return questions if questions else ["No questions could be generated from the available data."]

        except Exception as e:
            logger.error(f"Error generating follow-up questions: {str(e)}", exc_info=True)

            # Check for rate limit errors
            error_message = str(e)
            if "429" in error_message and "quota" in error_message:
                logger.warning("Gemini API rate limit exceeded for question generation")
                return [
                    "1. API rate limit reached. Please try again later.",
                    "2. What are the current blockers for critical issues?",
                    "3. How is the team workload distributed?",
                    "4. Are there any stale issues that require immediate attention?",
                    "5. What is our current sprint completion rate?"
                ]
            else:
                return [f"Error generating questions: {str(e)}"]

    def _generate_structured_summary(self, raw_analysis: str) -> Dict[str, Any]:
        """
        Generates the structured summary JSON from the raw analysis text using Gemini.

        Args:
            raw_analysis: The raw text analysis generated by Step 1.

        Returns:
            Dictionary containing the structured summary, or a dictionary with an 'error' key if failed.
        """
        logger.info("Initiating Step 2: Generating structured summary.")
        if not raw_analysis:
             logger.warning("Cannot generate structured summary: Raw analysis input is empty.")
             return {"error": "Input raw analysis was empty."}

        prompt = self._create_structured_summary_prompt()
        full_prompt = f"{prompt}\\n\\n--- Raw Analysis Text ---\\n{raw_analysis}"

        error_response = {"error": "Failed to generate or parse structured summary."} # Default error

        try:
            # Configure for JSON output if supported, otherwise rely on prompt instructions
            # Check SDK documentation if a specific 'response_mime_type' for JSON is reliable
            generation_config_json = self.generation_config_dict.copy()
            # Lower temperature for more deterministic JSON structure
            generation_config_json['temperature'] = 0.2
            # Potentially set response_mime_type if available and reliable:
            # generation_config_json['response_mime_type'] = 'application/json'

            # Use GenerationConfig, not GenerateContentConfig
            config = types.GenerationConfig(**generation_config_json)

            logger.debug("Sending request to Gemini for structured summary generation...")
            response = self.model.generate_content(full_prompt, generation_config=config)

            logger.debug("Received response from Gemini for Step 2.")

            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                # Combine text parts if response is multi-part (less likely for this prompt)
                structured_text = "".join(part.text for part in response.candidates[0].content.parts if part.text)

                # Clean the response text: remove potential markdown code fences
                structured_text = re.sub(r"^```json\s*|\s*```$", "", structured_text, flags=re.MULTILINE).strip()

                if not structured_text:
                     logger.warning("Gemini response for structured summary was empty.")
                     return {"error": "Gemini returned an empty response for structured summary."}

                try:
                    logger.debug(f"Attempting to parse JSON: {structured_text[:500]}...") # Log beginning of text
                    parsed_summary = json.loads(structured_text)

                    # Basic validation: Check if it's a dictionary with expected keys (adjust as needed)
                    expected_keys = ["daily_pulse", "risk_intelligence", "team_performance", "activity_summary"]
                    if isinstance(parsed_summary, dict) and all(key in parsed_summary for key in expected_keys):
                        # Move success log here
                        logger.info("Successfully generated and parsed structured summary.")
                        # Perform cleansing on the parsed summary as well
                        return self._cleanse_before_json(parsed_summary)
                    else: # Correctly indented else associated with the 'if' inside 'try'
                        logger.error(f"Parsed JSON does not match expected structure. Keys found: {list(parsed_summary.keys()) if isinstance(parsed_summary, dict) else 'Not a dict'}")
                        error_response["error"] = "Parsed JSON structure validation failed."
                        error_response["details"] = f"Expected keys: {expected_keys}"
                        return error_response # Return error if structure fails

                except json.JSONDecodeError as json_err:
                    logger.error(f"Failed to decode JSON response for structured summary: {json_err}")
                    logger.debug(f"Raw text received: {structured_text}") # Log full text on error
                    error_response["error"] = f"JSON Decode Error: {json_err}"
                    error_response["raw_response"] = structured_text # Include raw text in error dict
                    return error_response # Return error if JSON decode fails

            else: # Correctly indented else associated with the outer 'if response.candidates...'
                logger.warning("Gemini response for Step 2 contained no processable parts.")
                # Log finish reason / safety feedback
                if hasattr(response, 'prompt_feedback'):
                    logger.warning(f"Prompt Feedback: {response.prompt_feedback}")
                    error_response["details"] = f"Prompt Feedback: {response.prompt_feedback}"
                if response.candidates and hasattr(response.candidates[0], 'finish_reason'):
                    logger.warning(f"Finish Reason: {response.candidates[0].finish_reason}")
                    error_response["details"] = error_response.get("details","") + f" Finish Reason: {response.candidates[0].finish_reason}"

                return error_response

        except RateLimitError as rle: # Catch specific rate limit error if raised by step 1 or here
             logger.error(f"AI Step 2 Error: Rate limit exceeded - {rle}")
             return {"error": "Rate limited during structured summary generation."}
        except Exception as e:
            logger.error(f"Error in _generate_structured_summary: {e}", exc_info=True)
            error_response["error"] = f"Unexpected error: {str(e)}"
            return error_response # Return the error dict

        logger.info(f"Generated structured summary with {len(structured_summary)} keys.")
        return structured_summary

# --- Add RateLimitError Exception Class --- #
class RateLimitError(Exception): # Make sure class definition is at the correct indentation level (top-level)
    """Custom exception for API rate limit errors."""
    pass
# --- End Add Exception Class --- #

# Example usage (optional, for testing)
# ... (Example usage remains the same) ...

