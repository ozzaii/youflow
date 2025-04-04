"""
Data Explorer page for exploring and querying the raw YouTrack data.
"""
import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import plotly.express as px # Import Plotly

# Page config
st.set_page_config(
    page_title="Data Explorer - YouTrack Analytics",
    page_icon="🔍",
    layout="wide"
)

# Title
st.title("Data Explorer")
st.markdown("Explore and analyze the raw YouTrack data")

# Check if data is loaded
if 'data_processor' not in st.session_state or not st.session_state.data_loaded:
    st.warning("No data loaded. Please go to the main page and click 'Refresh Data'.")
    st.stop()

# Get data processor
data_processor = st.session_state.data_processor

# Create tabs for different data sets
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Issues", "Custom Fields", "Comments", "History", "Sprints"
])

# Issues tab
with tab1:
    st.header("Issues")
    
    if data_processor.issues_df is not None and not data_processor.issues_df.empty:
        # Filter options
        st.subheader("Filters")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Filter by assignee (multiselect)
            assignees = sorted(data_processor.issues_df['assignee'].dropna().unique().tolist())
            
            # Calculate top assignees based on open issues
            top_assignees = []
            try:
                assignee_workload = data_processor.get_assignee_workload()
                if not assignee_workload.empty:
                    top_assignees = assignee_workload.nlargest(3, 'open_issues')['assignee'].tolist()
            except Exception as e:
                st.warning(f"Could not determine top assignees: {e}")
                
            selected_assignees = st.multiselect("Assignees", assignees, default=top_assignees) # Pre-select top assignees
        
        with col2:
            # Filter by status (from custom fields)
            statuses = ['All']
            if data_processor.custom_fields_df is not None:
                status_field = data_processor.custom_fields_df[data_processor.custom_fields_df['field_name'] == 'State']
                if not status_field.empty:
                    statuses += sorted(status_field['field_value'].unique().tolist())
            
            selected_status = st.selectbox("Status", statuses)
        
        with col3:
            # Filter by resolution
            resolution_options = ['All', 'Resolved', 'Unresolved']
            selected_resolution = st.selectbox("Resolution", resolution_options)
        
        # Apply filters
        filtered_df = data_processor.issues_df.copy()
        
        # Updated assignee filter logic for multiselect
        if selected_assignees: # Check if the list is not empty
            filtered_df = filtered_df[filtered_df['assignee'].isin(selected_assignees)]
        
        if selected_status != 'All':
            # Get issues with the selected status
            status_issues = data_processor.custom_fields_df[
                (data_processor.custom_fields_df['field_name'] == 'State') & 
                (data_processor.custom_fields_df['field_value'] == selected_status)
            ]['issue_id'].tolist()
            
            filtered_df = filtered_df[filtered_df['id'].isin(status_issues)]
        
        if selected_resolution == 'Resolved':
            filtered_df = filtered_df[filtered_df['resolved'].notna()]
        elif selected_resolution == 'Unresolved':
            filtered_df = filtered_df[filtered_df['resolved'].isna()]
        
        # Display filtered issues
        st.subheader(f"Issues ({len(filtered_df)} records)")
        st.dataframe(filtered_df, use_container_width=True)
    else:
        st.info("No issue data available.")

# Custom Fields tab
with tab2:
    st.header("Custom Fields")
    
    if data_processor.custom_fields_df is not None and not data_processor.custom_fields_df.empty:
        # Filter options
        st.subheader("Filters")
        col1, col2 = st.columns(2)
        
        with col1:
            # Filter by field name
            field_names = ['All'] + sorted(data_processor.custom_fields_df['field_name'].unique().tolist())
            selected_field = st.selectbox("Field Name", field_names)
        
        with col2:
            # Filter by issue ID
            issue_id = st.text_input("Issue ID")
        
        # Apply filters
        filtered_df = data_processor.custom_fields_df.copy()
        
        if selected_field != 'All':
            filtered_df = filtered_df[filtered_df['field_name'] == selected_field]
        
        if issue_id:
            filtered_df = filtered_df[filtered_df['issue_id'] == issue_id]
        
        # Display filtered custom fields
        st.subheader(f"Custom Fields ({len(filtered_df)} records)")
        st.dataframe(filtered_df, use_container_width=True)
        
        # Show value distribution for selected field
        if selected_field != 'All':
            st.subheader(f"Value Distribution for {selected_field}")
            value_counts = filtered_df['field_value'].value_counts().reset_index()
            value_counts.columns = ['Value', 'Count']
            
            st.bar_chart(value_counts.set_index('Value'))
    else:
        st.info("No custom field data available.")

# Comments tab
with tab3:
    st.header("Comments")
    
    if data_processor.comments_df is not None and not data_processor.comments_df.empty:
        # Filter options
        st.subheader("Filters")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Filter by issue ID
            issue_id = st.text_input("Issue ID", key="comments_issue_id")
        
        with col2:
            # Filter by author
            st.subheader("Filter by Comment Author")
            if data_processor.comments_df is not None and not data_processor.comments_df.empty and 'author_name' in data_processor.comments_df.columns:
                authors = ['All'] + sorted(data_processor.comments_df['author_name'].unique().tolist())
                selected_author = st.selectbox("Select Author", authors)
            else:
                st.warning("Comment author data is not available or missing 'author_name' column.")
                selected_author = 'All'
        
        with col3:
            # Filter by date range
            date_range = st.date_input(
                "Date Range",
                value=(
                    datetime.now() - timedelta(days=30),
                    datetime.now()
                )
            )
        
        # Apply filters
        filtered_df = data_processor.comments_df.copy()
        
        if issue_id:
            filtered_df = filtered_df[filtered_df['issue_id'] == issue_id]
        
        if selected_author != 'All' and 'author_name' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['author_name'] == selected_author]
        
        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = filtered_df[
                (filtered_df['created'].dt.date >= start_date) & 
                (filtered_df['created'].dt.date <= end_date)
            ]
        
        # Display filtered comments
        st.subheader(f"Comments ({len(filtered_df)} records)")
        
        # Format display dataframe
        display_df = filtered_df.copy()
        display_df['created'] = display_df['created'].dt.strftime('%Y-%m-%d %H:%M')
        
        st.dataframe(display_df, use_container_width=True)
        
        # Show comment activity over time
        st.subheader("Comment Activity Over Time")
        if not filtered_df.empty:
            filtered_df['date'] = filtered_df['created'].dt.date
            comment_counts = filtered_df.groupby('date').size().reset_index()
            comment_counts.columns = ['date', 'count']
            
            st.line_chart(comment_counts.set_index('date'))
    else:
        st.info("No comment data available.")

# History tab
with tab4:
    st.header("Issue History")
    
    if data_processor.history_df is not None and not data_processor.history_df.empty:
        # Filter options
        st.subheader("Filters")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Filter by issue ID
            issue_id = st.text_input("Issue ID", key="history_issue_id")
        
        with col2:
            # Filter by field name
            field_names = ['All'] + sorted(data_processor.history_df['field_name'].unique().tolist())
            selected_field = st.selectbox("Field Name", field_names, key="history_field")
        
        with col3:
            # Filter by author
            authors = ['All'] + sorted(data_processor.history_df['author'].unique().tolist())
            selected_author = st.selectbox("Author", authors, key="history_author")
        
        # Apply filters
        filtered_df = data_processor.history_df.copy()
        
        if issue_id:
            filtered_df = filtered_df[filtered_df['issue_id'] == issue_id]
        
        if selected_field != 'All':
            filtered_df = filtered_df[filtered_df['field_name'] == selected_field]
        
        if selected_author != 'All':
            filtered_df = filtered_df[filtered_df['author'] == selected_author]
        
        # Sort by timestamp (most recent first)
        filtered_df = filtered_df.sort_values('timestamp', ascending=False)
        
        # Display filtered history
        st.subheader(f"Issue History ({len(filtered_df)} records)")
        
        # Format display dataframe
        display_df = filtered_df.copy()
        display_df['timestamp'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
        
        st.dataframe(display_df, use_container_width=True)
        
        # Show history activity by field
        if not filtered_df.empty:
            st.subheader("Activity by Field")
            field_counts = filtered_df['field_name'].value_counts().reset_index()
            field_counts.columns = ['Field', 'Count']
            
            st.bar_chart(field_counts.set_index('Field'))
    else:
        st.info("No history data available.")

# Sprints tab
with tab5:
    st.header("Sprints")
    
    if data_processor.sprint_df is not None and not data_processor.sprint_df.empty:
        # Count issues per sprint
        sprint_counts = data_processor.sprint_df['sprint_name'].value_counts().reset_index()
        sprint_counts.columns = ['Sprint', 'Issue Count']
        
        # Display sprint overview
        st.subheader("Sprint Overview")
        st.dataframe(sprint_counts, use_container_width=True)
        
        # Sprint selection
        selected_sprint = st.selectbox(
            "Select Sprint",
            options=['All'] + sorted(data_processor.sprint_df['sprint_name'].unique().tolist())
        )
        
        # Filter issues by sprint
        if selected_sprint != 'All':
            sprint_issues = data_processor.sprint_df[data_processor.sprint_df['sprint_name'] == selected_sprint]['issue_id'].tolist()
            
            # Get issue details
            sprint_issue_details = data_processor.issues_df[data_processor.issues_df['id'].isin(sprint_issues)].copy()
            
            # Add status
            if not sprint_issue_details.empty and data_processor.custom_fields_df is not None:
                sprint_issue_details['status'] = sprint_issue_details['id'].apply(
                    lambda x: data_processor.custom_fields_df[
                        (data_processor.custom_fields_df['issue_id'] == x) & 
                        (data_processor.custom_fields_df['field_name'] == 'State')
                    ]['field_value'].values[0] if len(data_processor.custom_fields_df[
                        (data_processor.custom_fields_df['issue_id'] == x) & 
                        (data_processor.custom_fields_df['field_name'] == 'State')
                    ]) > 0 else ''
                )
                
                # Display issues
                st.subheader(f"Issues in Sprint: {selected_sprint}")
                display_issues = sprint_issue_details[['id', 'summary', 'status', 'assignee', 'created', 'resolved']]
                display_issues['created'] = display_issues['created'].dt.strftime('%Y-%m-%d')
                display_issues['resolved'] = display_issues['resolved'].dt.strftime('%Y-%m-%d')
                
                st.dataframe(display_issues, use_container_width=True)
                
                # Status breakdown
                st.subheader("Status Breakdown")
                status_counts = sprint_issue_details['status'].value_counts().reset_index()
                status_counts.columns = ['Status', 'Count']
                
                st.bar_chart(status_counts.set_index('Status'))
            else:
                st.info(f"No issues found for sprint: {selected_sprint}")
    else:
        st.info("No sprint data available.")

# Add a custom query section
st.markdown("---")
st.header("Custom Query")
st.markdown("Run a custom query against the data")

query_type = st.selectbox(
    "Query Type",
    options=["Issues by Field Value", "Status Changes", "Assignee Changes", "Daily Activity"]
)

if query_type == "Issues by Field Value":
    # Select field
    if data_processor.custom_fields_df is not None:
        field_options = sorted(data_processor.custom_fields_df['field_name'].unique().tolist())
        selected_query_field = st.selectbox("Select Field", field_options)
        
        # Get possible values for the field
        field_values = sorted(data_processor.custom_fields_df[
            data_processor.custom_fields_df['field_name'] == selected_query_field
        ]['field_value'].unique().tolist())
        
        selected_values = st.multiselect("Select Values", field_values)
        
        if st.button("Run Query"):
            if selected_values:
                # Get issues with selected field values
                matching_issues = data_processor.custom_fields_df[
                    (data_processor.custom_fields_df['field_name'] == selected_query_field) & 
                    (data_processor.custom_fields_df['field_value'].isin(selected_values))
                ]['issue_id'].tolist()
                
                # Get issue details
                matching_issue_details = data_processor.issues_df[data_processor.issues_df['id'].isin(matching_issues)].copy()
                
                st.subheader(f"Issues with {selected_query_field} in {', '.join(selected_values)}")
                st.info(f"Found {len(matching_issue_details)} issues")
                
                if not matching_issue_details.empty:
                    st.dataframe(matching_issue_details, use_container_width=True)

elif query_type == "Status Changes":
    # Get status changes from history
    if data_processor.history_df is not None:
        status_changes = data_processor.get_status_transitions()
        
        # Filter options
        col1, col2 = st.columns(2)
        
        # Safely handle the case where the dataframe might be empty or missing columns
        from_options = ['Any']
        to_options = ['Any']
        
        if not status_changes.empty:
            if 'removed' in status_changes.columns:
                from_options += sorted(status_changes['removed'].dropna().unique().tolist())
            
            if 'added' in status_changes.columns:
                to_options += sorted(status_changes['added'].dropna().unique().tolist())
        
        with col1:
            from_status = st.selectbox(
                "From Status",
                options=from_options
            )
        
        with col2:
            to_status = st.selectbox(
                "To Status",
                options=to_options
            )
        
        if st.button("Run Query"):
            filtered_changes = status_changes.copy()
            
            if from_status != 'Any' and 'removed' in filtered_changes.columns:
                filtered_changes = filtered_changes[filtered_changes['removed'] == from_status]
            
            if to_status != 'Any' and 'added' in filtered_changes.columns:
                filtered_changes = filtered_changes[filtered_changes['added'] == to_status]
            
            # Sort by timestamp (most recent first) if the column exists
            if 'timestamp' in filtered_changes.columns:
                filtered_changes = filtered_changes.sort_values('timestamp', ascending=False)
            
            st.subheader(f"Status Changes: {from_status} → {to_status}")
            st.info(f"Found {len(filtered_changes)} transitions")
            
            if not filtered_changes.empty:
                # Format for display
                display_changes = filtered_changes.copy()
                display_changes['timestamp'] = display_changes['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
                
                st.dataframe(display_changes, use_container_width=True)

elif query_type == "Assignee Changes":
    # Get assignee changes from history
    if data_processor.history_df is not None:
        assignee_changes = data_processor.get_assignee_changes()
        
        if not assignee_changes.empty:
            # Filter options
            col1, col2 = st.columns(2)
            
            # Safely handle the case where the dataframe might be missing columns
            from_options = ['Any']
            to_options = ['Any']
            
            if 'removed' in assignee_changes.columns:
                from_options += sorted(assignee_changes['removed'].dropna().unique().tolist())
            
            if 'added' in assignee_changes.columns:
                to_options += sorted(assignee_changes['added'].dropna().unique().tolist())
            
            with col1:
                from_assignee = st.selectbox(
                    "From Assignee",
                    options=from_options
                )
            
            with col2:
                to_assignee = st.selectbox(
                    "To Assignee",
                    options=to_options
                )
            
            if st.button("Run Query"):
                filtered_changes = assignee_changes.copy()
                
                if from_assignee != 'Any' and 'removed' in filtered_changes.columns:
                    filtered_changes = filtered_changes[filtered_changes['removed'] == from_assignee]
                
                if to_assignee != 'Any' and 'added' in filtered_changes.columns:
                    filtered_changes = filtered_changes[filtered_changes['added'] == to_assignee]
                
                # Sort by timestamp (most recent first) if the column exists
                if 'timestamp' in filtered_changes.columns:
                    filtered_changes = filtered_changes.sort_values('timestamp', ascending=False)
                
                st.subheader(f"Assignee Changes: {from_assignee} → {to_assignee}")
                st.info(f"Found {len(filtered_changes)} transitions")
                
                if not filtered_changes.empty:
                    # Format for display
                    display_changes = filtered_changes.copy()
                    if 'timestamp' in display_changes.columns and not display_changes['timestamp'].empty:
                        display_changes['timestamp'] = display_changes['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
                    
                    st.dataframe(display_changes, use_container_width=True)
        else:
            st.info("No assignee change data available.")

elif query_type == "Daily Activity":
    # Analyze daily activity patterns
    if data_processor.history_df is not None:
        # Date range selection
        date_range = st.date_input(
            "Date Range",
            value=(
                datetime.now() - timedelta(days=30),
                datetime.now()
            )
        )
        
        if st.button("Run Query"):
            if len(date_range) == 2:
                start_date, end_date = date_range
                
                # Filter history by date range
                filtered_history = data_processor.history_df[
                    (data_processor.history_df['timestamp'].dt.date >= start_date) & 
                    (data_processor.history_df['timestamp'].dt.date <= end_date)
                ].copy()
                
                if not filtered_history.empty:
                    # Extract day and hour
                    filtered_history['date'] = filtered_history['timestamp'].dt.date
                    filtered_history['hour'] = filtered_history['timestamp'].dt.hour
                    filtered_history['day_of_week'] = filtered_history['timestamp'].dt.day_name()
                    
                    # Activity by date
                    st.subheader("Activity by Date")
                    date_counts = filtered_history.groupby('date').size().reset_index()
                    date_counts.columns = ['Date', 'Activity Count']
                    
                    st.line_chart(date_counts.set_index('Date'))
                    
                    # Activity by hour
                    st.subheader("Activity by Hour of Day")
                    hour_counts = filtered_history.groupby('hour').size().reset_index()
                    hour_counts.columns = ['Hour', 'Activity Count']
                    
                    st.bar_chart(hour_counts.set_index('Hour'))
                    
                    # Activity by day of week
                    st.subheader("Activity by Day of Week")
                    
                    # Define day order
                    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                    
                    # Create ordered categorical
                    filtered_history['day_of_week'] = pd.Categorical(
                        filtered_history['day_of_week'],
                        categories=day_order,
                        ordered=True
                    )
                    
                    day_counts = filtered_history.groupby('day_of_week').size().reset_index()
                    day_counts.columns = ['Day', 'Activity Count']
                    day_counts = day_counts.sort_values('Day')
                    
                    st.bar_chart(day_counts.set_index('Day'))
                    
                    # Activity by field
                    st.subheader("Activity by Field")
                    field_counts = filtered_history.groupby('field_name').size().reset_index()
                    field_counts.columns = ['Field', 'Activity Count']
                    field_counts = field_counts.sort_values('Activity Count', ascending=False)
                    
                    st.bar_chart(field_counts.set_index('Field'))
                else:
                    st.info("No activity data found in the selected date range.")
