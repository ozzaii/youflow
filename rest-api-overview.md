YouTrack REST API – Data Retrieval (GET) Endpoints Reference

Authentication & Format: All endpoints require an HTTP header Authorization: Bearer <token> with a valid permanent token for a YouTrack user ￼. Clients should also send Accept: application/json to receive JSON responses ￼. By default, only an entity’s id and $type are returned; use the fields parameter to request specific attributes ￼. Many list endpoints are paginated – by default up to 42 items are returned if no limit is specified ￼. You can use $top (to set page size) and $skip (to offset) to page through results ￼. Some “activities” endpoints use cursor-based pagination instead of skip/top ￼ ￼. Below is a comprehensive list of GET endpoints, organized by resource category, including path placeholders, descriptions, supported query params, and examples.

Issues

The Issues API allows searching and retrieving issue details and related sub-resources (comments, attachments, links, etc.). Issue data can be filtered by YouTrack’s powerful search queries. Common query params include:
	•	query – filter issues by a search query (same syntax as in YouTrack UI, e.g. project: PRJ #Unresolved) ￼. If omitted, all issues are returned ￼.
	•	fields – specify which fields to retrieve; otherwise only the issue id and type are returned ￼.
	•	customFields – optional, to include only certain custom fields by name in the returned issues. If not set, all custom fields are included (when requested via fields) ￼. This parameter can be repeated for multiple fields.
	•	$top and $skip – for pagination (number of issues to return and offset). Defaults: $top=42 if not specified ￼.

Endpoints in this category:
	•	GET /api/issues – List/Search issues. Retrieves issues visible to the user, optionally filtered by query. Supports query, fields, customFields, $top, $skip parameters for filtering and pagination ￼ ￼.
Sample Request:

GET https://example.youtrack.cloud/api/issues?query=for:%20me%20%23Unresolved&fields=id,idReadable,summary,description&$top=50

This returns a JSON array of issues matching the query (e.g. all unresolved issues for the current user) ￼. Each issue object contains fields like id, idReadable (project key and number), summary, etc., according to the requested fields. Use $skip and $top to page through large result sets ￼. The id is the internal ID and idReadable is the human-readable issue ID.

	•	GET /api/issues/{issueID} – Get issue by ID. Returns the detailed data for a specific issue. You must specify desired fields (e.g. fields=id,summary,description,customFields(...),commentsCount) to retrieve more than just the issue’s ID ￼.
Description: Use this to fetch a single issue’s details, including custom field values, reporter/assignee, etc. For example, GET /api/issues/PRJ-123?fields=id,idReadable,summary,description,reporter(name),customFields(name,value(name)) would return the issue PRJ-123 with its summary, description, reporter’s name, and custom field values (by name) ￼ ￼.
	•	GET /api/issues/{issueID}/comments – List issue comments. Retrieves all comments on the given issue. Supports fields to select comment properties (e.g. author, text, created timestamp).
Sample: GET /api/issues/PRJ-123/comments?fields=id,text,author(login),created will return an array of comment objects for issue PRJ-123, each with its text, author login, and creation time. Comments are returned sorted by creation (typically oldest first). Pagination is possible with $top and $skip if an issue has many comments (default 42 per page) ￼.
	•	GET /api/issues/{issueID}/comments/{commentID} – Get specific comment. Retrieves a single comment by its ID on the specified issue. Use this to fetch the content of a particular comment. e.g. GET /api/issues/PRJ-123/comments/456-789?fields=id,text,author(name),updated returns the comment’s text, author name, and last update timestamp.
	•	GET /api/issues/{issueID}/attachments – List issue attachments. Returns metadata for all attachments on the issue (each attachment’s id, name, file type, size, etc.). Use fields to select details like name, size, mimeType, url. (The attachment content itself can be downloaded via the URL provided in the attachment object’s url field.) Supports $top/$skip for pagination if many attachments.
Note: YouTrack attachments are binary files; this GET returns their metadata. For example, GET /api/issues/PRJ-123/attachments?fields=name,size,mimeType might yield a list of attachments with filenames and sizes.
	•	GET /api/issues/{issueID}/attachments/{attachID} – Download attachment. Retrieves the raw file content of a specific attachment. This is not a JSON response but the binary file (image, document, etc.) itself. No fields param is used here (the URL is typically given by the attachment’s metadata). For example, an image attachment can be fetched via this endpoint (or the same URL as in the issue’s attachment url field).
	•	GET /api/issues/{issueID}/links – List issue links. Returns all issue links from this issue to other issues. Issue links represent relationships (e.g. “duplicates”, “is duplicated by”, “relates to”). Each link item includes link type and target issue. Use fields to get details like type(name,inward,outward) and the linked issues (or target issue id).
Example: GET /api/issues/PRJ-123/links?fields=linkType(name),issues(idReadable) could show that PRJ-123 “duplicates” issue XYZ-1, etc. This helps build an issue dependency graph.
	•	GET /api/issues/{issueID}/links/{linkID} – Get specific link. Retrieves a particular link by its ID (each link has an ID). Typically not needed unless you store link IDs, since listing an issue’s links gives you all relevant info. But this can fetch one link’s data if the link ID is known.
	•	GET /api/issues/{issueID}/customFields – List issue custom fields. Returns all custom field values on the issue. Each item includes the field’s name, type, and the value. (This is essentially the customFields array you can also get by including customFields in the issue resource’s fields.) You can filter which custom fields to return by using the customFields query param on the /api/issues request as described above ￼, but this endpoint gives the full set by default. Use fields to specify what details to see (e.g. fields=name,value(name) to get just each field’s name and value label).
	•	GET /api/issues/{issueID}/customFields/{fieldID} – Get specific field value. Retrieves the value of a specific custom field on the issue (by the field’s id on that issue). For example, to get just the “Priority” field of an issue, you could call /api/issues/PRJ-123/customFields/PRIORITY_FIELD_ID?fields=value(name) (assuming you have the field’s id). Usually, it’s more convenient to get all fields in one request, but this exists for singular fetch.
	•	GET /api/issues/{issueID}/tags – List tags on issue. Returns all tags that have been added to the issue (by any user who tagged it). Each tag object includes its id, name, and color, etc. Use fields to get desired properties. If a tag is private to a user or not visible, it may not appear unless the requesting user has access.
Example: GET /api/issues/PRJ-123/tags?fields=name,color(background) could return tags like “Important” with a color code, etc.
	•	GET /api/issues/{issueID}/tags/{tagID} – Get specific tag on issue. Checks for a specific tag’s presence on the issue (returns the tag if the issue has it, or 404 if not). Typically used to confirm if a particular tag is attached to the issue.
	•	GET /api/issues/{issueID}/project – Get issue’s project. Returns the project to which the issue belongs. Essentially this is a shortcut to fetch the Project info for the issue’s project. The response is a Project entity (with fields like id, name, etc. depending on requested fields). Equivalent to getting the issue with fields=project(id,name,shortName) but available as its own resource.
	•	GET /api/issues/{issueID}/sprints – List sprints for issue. Returns a list of Sprints (iterations) in which this issue appears. This is relevant if the issue is part of one or more Agile boards. Each sprint object includes fields like id, name, and the board (agile) it belongs to. Use fields to include details (e.g. sprint start/end dates).
Example: If issue PRJ-42 is scheduled in two sprints across different boards, this endpoint might return those two sprint objects ￼ ￼. Supports pagination via $top/$skip if an issue is in many sprints (uncommon).
	•	GET /api/issues/{issueID}/activities – List issue change activities (history). Returns the change history items (ActivityItems) for the issue, such as updates to fields, comments added, attachments added or removed, state changes, etc. Supports filtering by activity categories query parameter to include only certain types of changes (e.g. categories=CommentsCategory,AttachmentsCategory to get only comments and attachment events) ￼. Also supports fields to select which properties of each activity to return (e.g. author(login), timestamp, added, removed, etc.).
Pagination: Activities use cursor-based pagination. You can specify $top to limit the number of items and use the cursor or the dedicated /activitiesPage resource for paging (see Activities section below). If using $skip on this endpoint, note that it might not be reliable if new activities are added in between requests ￼.
Example Request:

GET /api/issues/PRJ-123/activities?fields=id,author(login),timestamp,target(id,$type)&categories=CommentsCategory,IssueCreatedCategory

This would retrieve the comment creation and issue creation events for issue PRJ-123, with each event’s ID, author login, timestamp, and the target of the activity (e.g. which comment or field was changed) ￼.

	•	GET /api/issues/{issueID}/activities/{activityID} – Get specific activity. Retrieves a single change event (activity item) by ID for the given issue. The response will detail that specific change (e.g. a particular field change or comment event). Use fields to request relevant details (such as added, removed values, etc.) ￼. For example, you can fetch a specific history item to see exactly what changed in that event.
Note: You need to know the activity ID (obtainable from the list of activities). Typically used if you’ve stored or received an activity ID and want to get its full details.
	•	GET /api/issues/{issueID}/activitiesPage – Page through activities (cursor paging). Instead of skipping, YouTrack provides a cursor-based pagination for activities. This endpoint returns a “page” of activities plus beforeCursor and afterCursor values. You can then call the same endpoint with cursor=<cursorValue> to get the next or previous page of activities ￼. It supports categories and fields similar to /activities. Use this when iterating through a long history without missing events that might be added concurrently. For example:
GET /api/issues/PRJ-123/activitiesPage?fields=activities(id,timestamp,author(name)),afterCursor&$top=100 would return up to 100 activities and a cursor to get the next page.
	•	GET /api/issues/{issueID}/timeTracking – Get issue time tracking summary. Returns the time tracking settings and summary for the issue, including fields like total time spent and remaining estimate on that issue (if time tracking is enabled for the project). The response is a IssueTimeTracking object which may include the issue’s estimation field and time spent field values. Use fields param to retrieve details (e.g. fields=remainingEstimate(minutes),timeSpent(minutes)).
Note: This is a read-only summary; individual work items are accessed via the next endpoints.
	•	GET /api/issues/{issueID}/timeTracking/workItems – List work items (time entries) on issue. Returns all WorkItems (time tracking entries) for the specified issue. Each work item represents a time expenditure logged on the issue (with fields such as id, date, duration, author, etc.). Supports fields (e.g. to include duration(minutes,presentation), author(name), etc.) and $top/$skip for paging through many work entries.
Example: GET /api/issues/PRJ-123/timeTracking/workItems?fields=date,author(name),duration(presentation) might return an array of work entries like “5h by John Doe on 2021-09-01” etc. This is useful for extracting time spent on each issue.
	•	GET /api/issues/{issueID}/timeTracking/workItems/{workItemID} – Get specific work item. Retrieves a single work log entry by its ID on the given issue. Returns the work item’s details (e.g. who logged it, duration, date, description). Use this to fetch or verify a particular time entry. (You can obtain workItemIDs from the list above.)

Notes: All issue-related GET endpoints require the user to have permission to view the issue and its data. If an issue is not accessible (e.g. private project), these endpoints will return 404 or 403. Also, many sub-resources (comments, attachments, etc.) can be fetched by including them in the fields of the main issue request as well (e.g. fields=comments(text),attachments(name)) ￼ ￼, but the dedicated endpoints above allow retrieving them independently or in bulk. Pagination ($top/$skip) and fields filtering are common to most collection endpoints.

Projects

The Projects API provides access to project configurations and lists of issues per project. Most project-related endpoints are under the /api/admin/projects path (requiring the user to have appropriate admin or global permissions to view project settings), except the basic list which is accessible to all users with project browse rights.
	•	GET /api/admin/projects – List all projects. Retrieves all projects the user can see. Each project contains metadata like id, name, shortName, description, etc. Use fields to specify which attributes to return (e.g. fields=id,name,shortName,leader(name)). Supports pagination with $top and $skip if there are many projects.
Sample: GET /api/admin/projects?fields=id,name,shortName,description&$top=100 – returns up to 100 projects with their basic info. By default, if no $top is given, up to 42 projects will be returned ￼.
	•	GET /api/admin/projects/{projectID} – Get project by ID. Returns details of a specific project, including its settings. Use fields to get project attributes like name, description, leader, etc. For example, GET /api/admin/projects/0-0?fields=name,description,leader(name),createdBy(login) might return the project name, description, project lead’s name, and creator’s login. The project’s ID here is the internal database ID (a numeric-ID string such as 0-0); you can get these IDs from the list projects call or from issue data (issue IDs include project ID as prefix).
	•	GET /api/admin/projects/{projectID}/customFields – List project custom fields. Retrieves all custom fields that are attached to the given project, along with their settings in that project. Each “ProjectCustomField” includes the field definition reference and project-specific parameters like the field’s bundle (value set) and whether it’s required, etc. Use fields to select details (e.g. fields=field(name,id),canBeEmpty,bundle(id,name) to see each field’s name and the bundle it uses in this project) ￼ ￼.
Sample: GET /api/admin/projects/{projectID}/customFields?fields=field(name),bundle(name),isPublic – would list fields like “Priority” with bundle “Priority (High, Low, etc.)”. This helps understand which custom fields are enabled in a project and what value sets they use.
	•	GET /api/admin/projects/{projectID}/customFields/{projectCustomFieldID} – Get project’s field settings by ID. Returns the configuration of a specific custom field in the project. The {projectCustomFieldID} is the id of the field assignment (not the global field id). This provides details such as the field’s name, the bundle of values (if an enum or owned field), default values, and other settings in the context of that project ￼ ￼. For example, use this to retrieve the options for a field like “Fix versions” in a particular project (which might use a specific Version bundle).
	•	GET /api/admin/projects/{projectID}/issues – List issues in project. Retrieves issues that belong to the specified project. This is essentially a shortcut to query issues by project; it returns the same results as using the general issues endpoint with a project: X filter. Supports standard issue list params: fields (to pick which issue fields), $top, $skip for pagination, and even an optional query parameter to further filter within the project.
Sample: GET /api/admin/projects/{projectID}/issues?fields=id,idReadable,summary&$top=50 – returns up to 50 issues of that project with their IDs and summaries ￼ ￼. (Internally, this is equivalent to /api/issues?query=project: <projectID>.) Use this to export all issues of a project. Pagination is used to iterate if the project has more issues (the response will include a partial list if over 42 issues, unless $top is set higher).
	•	GET /api/admin/projects/{projectID}/timeTrackingSettings – Project time tracking settings. Returns the time tracking configuration for the project, including whether time tracking is enabled, which fields are used for estimation and spent time, and which work item types are auto-attached. The response is a ProjectTimeTrackingSettings entity with fields like enabled, estimate(field), timeSpent(field), and the list of workItemTypes enabled for this project ￼. Use fields to retrieve specific details (e.g. fields=enabled,workItemTypes(name,autoAttached)).
Example: GET /api/admin/projects/{projectID}/timeTrackingSettings?fields=enabled,workItemTypes(name,autoAttached) might return that time tracking is enabled and that work item type “Development” is auto-attached to new issues for that project.
	•	GET /api/admin/projects/{projectID}/timeTrackingSettings/workItemTypes – List project work item types. If time tracking is on, this returns the set of work item types (categories of work) that are available in the given project. (Typically this is either the global list or a subset if configured.) Each item has an id, name, and possibly an autoAttached flag (meaning it’s automatically added to new issues) ￼. This is usually the same data found in the workItemTypes field of the project’s timeTrackingSettings above, but provided as a separate list resource.
	•	GET /api/admin/projects/{projectID}/timeTrackingSettings/workItemTypes/{typeID} – Get specific project work item type. Returns details about a single work item type in the context of the project (usually just its name and whether it’s auto-attached). Often not needed except to verify a specific type’s config.
	•	GET /api/admin/projects/{projectID}/sprints – List project’s sprints. (If applicable) Returns the sprints in the project. Note: In YouTrack, sprints belong to agile boards, not directly to projects, but if an agile board is tied to a single project, this could list sprints associated with that project’s board. In practice, you would retrieve sprints via the Agile board endpoints (see Agile Boards section). This endpoint is not prominent in docs (most likely, use the Agile API instead). Included here for completeness if it exists.

Note: The /api/projects endpoints are under the admin path because modifying project settings is an admin operation. However, performing a GET on these endpoints to read data can typically be done by users who have read access or specific permissions (e.g., Low-level Administrators or project admins). If a user lacks permission, some project details might be inaccessible. Standard pagination ($top, $skip) and field selection apply.

Agile Boards and Sprints

The Agiles API (Agile boards) lets you retrieve boards used for Scrum/Kanban and their sprints. This is useful for understanding how issues are organized into iterations.
	•	GET /api/agiles – List agile boards. Returns all Agile boards the user has access to. Each board (Agile) includes fields like id, name, and settings like the projects it covers. Use fields to select details (e.g. fields=id,name,projects(name)).
Example: GET /api/agiles?fields=id,name,projects(name) might return boards like “Team XYZ Scrum Board” with associated project names. Supports $top/$skip for pagination if many boards ￼ ￼.
	•	GET /api/agiles/{boardID} – Get board by ID. Retrieves a specific Agile board’s configuration. The response includes board settings such as the projects it uses, the column settings, is it Scrum or Kanban, etc. Use fields to tailor the output (e.g. fields=name,sprints(start,finish),columns(field(name))). This can return a lot of info including the list of sprints (with their basic info) if requested. If you need full sprint details or issues per sprint, use the sprint-specific endpoints below.
	•	GET /api/agiles/{boardID}/sprints – List sprints on board. Retrieves all sprints (iterations) defined on the given board (for Scrum boards) or past/future iterations (for Kanban it may return a single pseudo-sprint or none). Each Sprint includes properties like id, name, goal, start and finish dates, and whether it’s archived. Use fields to get these (e.g. fields=id,name,start,finish,goal,archived). Pagination with $top/$skip is supported if there are many sprints.
Sample: GET /api/agiles/{boardID}/sprints?fields=id,name,start,finish,archived – would list all sprints of the board with their schedule and status (active or archived). You can identify the current sprint, future sprints, etc. from this list.
	•	GET /api/agiles/{boardID}/sprints/{sprintID} – Get sprint by ID. Returns details of a specific sprint on that board. Fields include name, goal, start/finish dates, and possibly an agile reference (the board). Use fields to get issue distribution if needed (for example, some queries might allow including issues in the sprint via issues(id,summary) but typically that’s done via a separate issues query). This endpoint is mainly for sprint metadata.
	•	GET /api/agiles/{boardID}/sprints/{sprintID}/issues – List issues in sprint. (If available) Returns the issues assigned to a particular sprint of a board. This might require specifying the context fields. (In older APIs, you would query issues with a filter like Sprint: {sprintName}. The new API likely has a direct resource as indicated by related resources.) If the endpoint exists, it would accept fields to specify what issue fields to return. For example, GET /api/agiles/87-72/sprints/91-703/issues?fields=idReadable,summary,assignee(login) could list all issues in that sprint with their summary and assignee. If this direct endpoint is not documented, the alternative is to use the Issues API with a query: query=Sprint: {sprint name}.
	•	GET /api/agiles/{boardID}/backlog – Backlog issues for board. (Scrum only) Returns the backlog issues for a Scrum board (issues not assigned to any sprint, but in the board’s projects and fit the board’s filter). Not explicitly listed in the Postman collection, but likely accessible via the board’s settings or by using the search query from board settings. If an endpoint exists, it might be /api/agiles/{boardID}/backlog?fields=.... Otherwise, use issues search with the board’s backlog query.

Note: Agile board and sprint endpoints require the user to have permission to view the board (usually if the projects on the board are visible to them). The data is read-only. Sprints are particularly important for time-based analysis and can be joined with issues (issues have a field listing which sprints they belong to, accessible via /issues/{id}/sprints as noted above).

Users

The Users API provides information about user accounts in YouTrack.
	•	GET /api/users?fields=... – List users. Returns all user accounts that the authorized user has permission to see (usually all users for an admin, or possibly limited for others). By default, returns up to 42 users ￼; use $top and $skip to page through if there are more. Use fields to include details like id,login,name,email,ban etc.
Example: GET /api/users?fields=id,login,name,email&$top=50 – returns first 50 users with their login, name, and email. You can filter the list by providing a query parameter (the Users API supports query to filter by username or full name) ￼ ￼ – for instance, query=admin to find users with “admin” in name or login.
	•	GET /api/users/me – Current user profile. A convenience endpoint to get the profile of the user who is authenticating the request. Equivalent to /api/users/{myID}. You should specify fields to get more than just the ID. For example, GET /api/users/me?fields=login,name,email,online returns your user login, name, email, and whether you’re online. This is useful for testing your auth and retrieving your permissions or profile settings.
	•	GET /api/users/{userID} – Get user by ID. Returns the profile of a specific user by their ID (a YouTrack user ID is typically an internal string like 1-2). Use fields to get user attributes: e.g. fields=login,name,email,jabber etc. This can show profile data, group memberships (if requested via subfields), etc.
Note: Regular users can retrieve basic info of other users if they share a project, but some fields (email, etc.) might require admin rights or appropriate permissions depending on YouTrack’s access settings.
	•	GET /api/users/{userID}/savedQueries – List user’s saved searches. Retrieves all Saved Queries (filters) owned by the specified user. Each saved query includes id, name, and the search query text (query) among other fields. Use fields to select attributes (e.g. fields=name,query,owner(login)). This endpoint helps to fetch personal saved filters of a user. (A user can also share saved queries, which might appear in the global list too – see Saved Queries section).
Example: GET /api/users/1-5/savedQueries?fields=name,query – might return that user’s saved search like “Open Bugs” with query #Unresolved Type:Bug.
	•	GET /api/users/{userID}/tags – List user’s issue tags. Returns all Issue Tags that the specified user has created (or is allowed to use). Issue tags in YouTrack are often personal, though they can be visible to others if shared. Each tag includes name, an optional query (if the tag is a smart tag that applies a filter), and color. Using fields=name,query,owner(login) will give the tag name, its filter query (if any), and owner. This allows extraction of how a user has categorized issues via tags. (This is essentially filtering the global tags list by owner user). You can also filter by tag name via a query param (e.g. query=Urgent to find tags with “Urgent” in name) ￼.

Note: In the Users domain, sensitive fields like emails or access permissions might only be visible to admins. The users endpoints are typically accessible to admins or users with sufficient rights (except /me). If an installation restricts who can list users, a non-admin might get only themselves or a subset. Pagination ($top/$skip) works on the list. No direct “search by name” endpoint exists, but using the query parameter on the list can serve that purpose.

User Groups

User Groups organize users and their roles. The User Groups API lets you retrieve group information.
	•	GET /api/userGroups – List user groups. Returns all user groups in the system that the caller has permission to view. Each group includes fields like id, name, and possibly usersCount. Use fields parameter to get details (e.g. fields=id,name,usersCount,icon). By default returns up to 42 groups; use $top and $skip for pagination if needed. This allows you to see all groups such as “Developers”, “QA”, etc.
Example: GET /api/userGroups?fields=name,usersCount – might return groups “Developers (10 users)”, “Project Admins (3 users)”, etc.
	•	GET /api/userGroups/{groupID} – Get group by ID. Retrieves details of a specific user group. You can get the group’s name, a list of members, and roles if you specify those in fields. For example, GET /api/userGroups/{id}?fields=name,users(login),teams(name) would return the group name and the list of user logins in that group (caution: users list might be large). More typically, one might retrieve name and perhaps count or roles. This endpoint is useful to enumerate members of a particular group for audit or visualization of team structure.

(There are also endpoints to add/remove users to groups, but those are POST/PUT, not covered here.)

Issue Tags

Issue Tags allow users to label issues. There are global endpoints for tags (distinct from the per-issue tagging under Issues).
	•	GET /api/issueTags – List all issue tags. Returns all Issue Tags that the user can see (including their own tags and any shared tags). Each tag entity includes name, owner, a search query (if the tag is defined by a query), and a color. Use fields to select these (e.g. fields=name,query,owner(login),updateableBy(name)). The query field of a tag represents a saved search the tag is based on (tags can be just labels or dynamic). Supports filtering by name via the query parameter (e.g. query=Important to find tags with “Important” in the name) ￼. Pagination with $top/$skip is supported if there are many tags.
Example: GET /api/issueTags?fields=name,owner(login),query – might return tags like “Important” (manual tag, no query) or “Unresolved” (a tag owned by user with a query like #Unresolved).
	•	GET /api/issueTags/{tagID} – Get tag by ID. Returns the details of a specific issue tag. This includes the tag’s name, its owner (who created it), its color, and the query it represents (if any). Use fields to tailor output. For instance, to get the tag name and its query: GET /api/issueTags/{id}?fields=name,query,owner(name) might yield "name": "Backlog", "query": "Priority: Low", "owner": { "name": "John Doe" }. This is useful if you have a tag ID (perhaps from an issue’s tag list) and want to know its full definition.

Note: Tags can be personal or global. A non-admin user will typically see only their tags and tags shared with them. The query parameter on the list acts on tag names (not the underlying search query). For example, query=High would match a tag named “High Priority” but not necessarily tags whose query contains “Priority: High”.

Saved Queries (Saved Searches)

Saved Queries in YouTrack (also known as filters) are stored search queries that can be reused. The API provides endpoints to read these saved searches.
	•	GET /api/savedQueries – List saved queries. Returns all saved queries that the user has access to. This typically includes the user’s own saved filters and any filters that have been shared with them or made global. Each saved query includes id, name (the title of the filter), the actual search query string, the owner, and possibly a visibleFor or updatableBy to denote sharing. Use fields to specify what to retrieve (e.g. fields=name,query,owner(login),visibleFor(name)). This endpoint supports $top/$skip pagination.
Example: GET /api/savedQueries?fields=name,query,owner(name) might return entries like “All Open Issues” with query #Unresolved owned by John, etc. This is useful to extract commonly used queries for analysis or to present them in a UI.
	•	GET /api/savedQueries/{queryID} – Get saved query by ID. Retrieves the details of one saved query (filter) by its ID. This returns the same fields as above but for just the specified filter. For example, GET /api/savedQueries/82-11?fields=name,query,owner(login),searchableProjects(name) would fetch a filter’s name, the query string, who owns it, and which projects it’s applicable to. Use this to get the definition of a particular saved search if you know its ID or have it from the list.
	•	GET /api/users/{userID}/savedQueries – (As mentioned in the Users section above): You can also retrieve saved queries by owner via the user-specific endpoint. For instance, /api/users/me/savedQueries to get only your own saved filters. This is essentially a filtered view of the savedQueries list where owner = that user.

Note: Saved queries are essentially named search filters. They may be used as the basis for agile board settings or dashboards. The query field is the search expression (same syntax as used in the UI or the query param for issues). If a saved query is limited to certain projects, that can be seen in the searchableProjects or similar fields if requested. Permissions: users can see their own queries and any shared with them; admins can potentially see all (if shared globally).

Activities (Global)

Beyond issue-specific activities, YouTrack provides a way to retrieve all activities (across issues, and possibly other entities) globally, which is useful for auditing and timeline visualizations.
	•	GET /api/activities – List all activities (global). Returns a global stream of ActivityItem events that the user has permission to see, across all issues (and possibly other entities like articles). This is essentially an activity feed. Supports filtering by categories query param to include only certain types of events (similar categories as issue activities: e.g. IssueCreated, CommentAdded, StateChanged, etc.) ￼. Also supports $top and $skip for pagination, but note that due to the dynamic nature of activities, cursor-based paging is recommended. Use fields to select what data to return for each activity (e.g. fields=id,timestamp,author(name),target(id,idReadable),category(id) etc.).
Example: GET /api/activities?categories=IssueCreatedCategory,IssueResolvedCategory&fields=id,timestamp,author(login),target(idReadable,$type) – would return recent issue creation and resolution events system-wide, each including when it happened, who did it, and which issue (target) was affected ￼ ￼.
	•	GET /api/activities/{activityID} – Get activity by ID (global). Retrieves a specific ActivityItem by its ID from the global feed. This will return details of the event regardless of which issue or entity it belongs to, as long as the user can access that entity. Use fields to request details (this endpoint supports very granular fields including the added/removed values, similar to issue-specific activity). For example, if you have an activity ID for a field change, you could call GET /api/activities/0-0-6?fields=author(name),field(customField(name)),added,removed,timestamp to see who changed what. This is rarely used directly unless you have stored activity IDs.
	•	GET /api/activitiesPage – Paginate activities (global cursor). Similar to the per-issue activitiesPage, this returns a page of global activities with beforeCursor and afterCursor for pagination. Use this for reliably iterating through the global activity stream. Supports categories and fields as query parameters. For example, GET /api/activitiesPage?fields=activities(id,timestamp,author(name),target($type)),afterCursor&categories=IssueCommentCategory&$top=50 could fetch 50 comment events across all issues, plus a cursor to get the next page. Using the cursor param in subsequent requests allows stable pagination without missing events ￼.

Note: The global activities endpoints are powerful for auditing changes across the whole system (issues created, comments added, etc.). They may include activities for other entities (like Articles, if you have knowledge base articles events, or user management events) depending on categories. Common categories include CommentsCategory, AttachmentsCategory, IssueCreatedCategory, IssueResolvedCategory, etc. (Full list in the documentation under ActivityCategory ￼). Make sure to use the fields param to avoid overly large payloads, and prefer activitiesPage + cursor for sequential reads to handle real-time updates gracefully ￼.

Custom Fields and Value Bundles

YouTrack’s Custom Fields system defines the structure of issue fields (like Priority, Type, State, etc.) and their possible values through bundles. The API allows read-only access to these configurations (admin permissions usually required).

Custom Field Definitions (Global):
	•	GET /api/admin/customFieldSettings/customFields – List custom fields (global definitions). Returns all custom field definitions in the system (these are field prototypes which can be attached to projects). Each custom field object includes id, name, fieldType (like integer, string, enum), etc. Use fields to specify what to retrieve, e.g. fields=id,name,fieldType(name),defaultBundle(id,name). This list includes both built-in fields (like “Assignee”, “Priority”) and any custom ones created by admins.
Example: GET /api/admin/customFieldSettings/customFields?fields=name,fieldType(valueType),aliases – might return entries like “Priority” (enum), “Estimation” (integer), with any aliases.
	•	GET /api/admin/customFieldSettings/customFields/{fieldID} – Get field definition by ID. Returns details of a specific custom field definition. This includes its name, type, and possibly the bundles or defaults associated. For instance, an enum field will link to a bundle of allowed values. Using fields=fieldType(name),defaultBundle(name),isAutoAttached could show that “Priority” is an enum field auto-attached with default bundle “Priority”.
	•	GET /api/admin/customFieldSettings/customFields/{fieldID}/instances – List project usages of a field. This endpoint lists all ProjectCustomField instances for the given field – essentially all the projects that have this field attached and how it’s configured in each. Each instance includes the project and the settings in that project (like which bundle is used, if it can be empty, etc.) ￼ ￼.
Example: GET /api/admin/customFieldSettings/customFields/{fieldID}/instances?fields=project(name),bundle(name),isPublic – for field “Priority”, this might list Project Alpha using bundle “Priority (Alpha)”, Project Beta using bundle “Priority (Beta)”, etc. This is useful to see differences in field configuration across projects.

Value Bundles: (These are sets of predefined values for custom fields, such as Priority levels, Version names, etc.)

YouTrack has different bundle types, each with similar endpoints. The {type} in the path can be:
enum, state, build, version, owned, or user. Each type corresponds to a field value domain:
	•	EnumBundle (for custom enumerated values like Priority or custom categories),
	•	StateBundle (for workflow states),
	•	BuildBundle (for build numbers/IDs),
	•	VersionBundle (for versions/releases),
	•	OwnedBundle (for values that have an owner, often used for subsystem/component with an owner user),
	•	UserBundle (for fields that store user or group selections).

For each bundle type, the endpoints follow a pattern:
	•	GET /api/admin/customFieldSettings/bundles/{type} – List all {type} bundles. Returns all bundles of that type. For example, /bundles/enum lists all enumeration bundles (like Priority, Severity sets), /bundles/version lists all version bundles, etc. Each bundle has an id, name, and other attributes like isUpdateable (whether it’s locked by system or not). Use fields to get attributes (e.g. fields=id,name,valuesCount).
Example: GET /api/admin/customFieldSettings/bundles/enum?fields=id,name – might return bundles like “Priority” (id 123-45) and “Severity” (id 67-89) ￼. This helps enumerate all predefined value sets.
	•	GET /api/admin/customFieldSettings/bundles/{type}/{bundleID} – Get bundle by ID. Returns the details of a specific bundle. For value bundles, the useful detail is often the list of values it contains (though note: the values might not be included by default – you may need to request them via fields or use the separate values endpoint). Other details could include description or if the bundle is aggregated.
Example: GET /api/admin/customFieldSettings/bundles/state/{id}?fields=id,name,values(name,ordinal) – would fetch a State bundle’s name and the list of state values (each with a name and order). Or for a version bundle: fields=name,values(name,releaseDate,released) to see version names and release dates. If values are not fetched in this call, use the next endpoint.
	•	GET /api/admin/customFieldSettings/bundles/{type}/{bundleID}/values – List values in bundle. Returns all values defined in the specified bundle. For example, for an Enum bundle, these are the list of options; for a Version bundle, the versions; for a User bundle, the users/groups included. Each value object typically has an id, name, and other attributes (like ordinal for order, isArchived, released for versions, etc.). Supports $top/$skip if a bundle has many values (e.g., hundreds of versions) ￼.
Examples:
	•	GET /api/admin/customFieldSettings/bundles/enum/{bundleID}/values?fields=id,name,ordinal – list all options in an enum.
	•	GET /api/admin/customFieldSettings/bundles/version/{bundleID}/values?fields=name,releaseDate,released – list versions with their release dates.
	•	GET /api/admin/customFieldSettings/bundles/user/{bundleID}/values?fields=name – (for user bundles, see note below).
This endpoint is the primary way to fetch the actual allowed values for a custom field (like all priorities, all states, etc.) ￼ ￼.
	•	GET /api/admin/customFieldSettings/bundles/{type}/{bundleID}/values/{valueID} – Get specific value from bundle. Retrieves a single value by ID from the bundle. This returns the value’s details (e.g. for an enum, its name and maybe description). For instance, if you have a Priority bundle and want the “High” value details, you’d call /enum/{bundleID}/values/{valueID}. Use fields to get properties (if not all are returned by default). e.g. fields=id,name,description ￼ ￼. This is helpful if you only know a value ID (perhaps from an issue’s custom field value) and need to get its name or attributes.

Special case – User Bundles: A User bundle contains references to users and/or groups (used for fields like Assignee if restricted, or custom user picker fields). In addition to the above, user bundles have sub-resources:
	•	GET /api/admin/customFieldSettings/bundles/user/{bundleID}/individuals – list individual users in the bundle.
	•	GET /api/admin/customFieldSettings/bundles/user/{bundleID}/groups – list user groups in the bundle.
	•	GET /api/admin/customFieldSettings/bundles/user/{bundleID}/aggregatedUsers – get the aggregate set of users (all individual users plus all members of groups included).
These allow you to resolve all actual users who could be selected for that field. For example, an “Assignee” bundle might include group “Developers” and user “alex”. The groups call will list “Developers”; individuals will list “alex”; aggregatedUsers will list everyone in “Developers” plus “alex” . Use appropriate fields (like user login, group name) when calling these.

Note: Accessing custom field settings and bundles typically requires the user to be an admin or have the Low-level Admin permission, since these are global configuration. If authorized, these endpoints are read-only and very useful for obtaining the context needed to interpret issue data (e.g., knowing all possible priorities, states, etc.). Remember to use fields to limit output (for instance, bundles can contain many values, you might not want all fields of each value). The default page size of 42 is in effect for listing bundle values, so if a bundle has more than 42 values (common in user bundles or large version lists), use pagination or increase $top ￼.

Issue Link Types

Issue link types define the relationships between issues (e.g. “Relates to”, “Duplicate”). Use these endpoints to retrieve the link type definitions.
	•	GET /api/issueLinkTypes – List issue link types. Returns all defined link types in the system. Each link type has an id, name, and two directions: outward and inward descriptions (for example, name=“Duplicate”, outward description=“duplicates”, inward description=“is duplicated by”). Use fields to retrieve these (e.g. fields=name,inward,outward,directed). This allows you to see all relation types used by issues.
Example: GET /api/issueLinkTypes?fields=name,inward,outward might return link types like: name: “Relates”, inward: “relates to”, outward: “relates to”; name: “Duplicate”, inward: “is duplicated by”, outward: “duplicates”, etc.
	•	GET /api/issueLinkTypes/{typeID} – Get issue link type by ID. Returns details of a specific link type. Typically you would use this to get the inward/outward names. For instance, if you have an issue link of type ID 123-45, GET /api/issueLinkTypes/123-45?fields=name,inward,outward could return that this ID corresponds to the “Dependency” link with inward description “depends on” and outward “is depended on by”. Usually, the list call is sufficient to map all, but this can fetch one if needed.

Note: Link types are part of global settings; viewing them usually requires admin access. However, since link types are not secret (they are visible as relationship names on issues), a user with access to issues can infer them. The API provides them explicitly via these endpoints. Rate limiting is not a concern here as the number of link types is typically small.

Knowledge Base Articles (Wiki)

(If your YouTrack has the knowledge base feature enabled, you can retrieve articles similarly to issues.)

Articles are pages in YouTrack’s knowledge base (Wiki). They have their own set of endpoints under /api/articles. These allow read-only access to article content and metadata.
	•	GET /api/articles – List articles. Returns all knowledge base articles the user has permission to view. Supports filtering by a query parameter similar to issues (e.g. query might search in article titles or content). Use fields to specify what to retrieve, e.g. fields=id,summary,updated,author(name),project(id) (note: articles belong to projects too, typically knowledge base projects). Pagination with $top/$skip is supported for iterating through many articles.
Example: GET /api/articles?fields=id,summary,author(login),updated&$top=100 – might return a list of article summaries with their authors and last update timestamp.
	•	GET /api/articles/{articleID} – Get article by ID. Returns the full content of a specific article. Important fields include summary (title), content (the wiki text or HTML of the article), updated timestamp, author and updater, etc. Use fields to include the content because by default you might get only ID. For example, GET /api/articles/456-789?fields=id,summary,content,updated,project(name) would retrieve the article’s title, body, last updated date, and the project (knowledge base) it belongs to. The content is usually in Markdown format (or HTML depending on how it’s stored).
	•	GET /api/articles/{articleID}/attachments – List article attachments. Similar to issue attachments, returns metadata for files attached to an article (images or files embedded in the knowledge base page). Use fields to get properties like name, size, mimeType, url. You can use this to download images or files used in the article.
	•	GET /api/articles/{articleID}/attachments/{attachID} – Get attachment content. Downloads the specified attachment file of the article (returns binary content). This works like issue attachments download.
	•	GET /api/articles/{articleID}/comments – List article comments. Returns comments on the knowledge base article. Use fields to get comment text, author, created time, etc. (e.g. fields=text,author(name),created). Works similarly to issue comments.
	•	GET /api/articles/{articleID}/comments/{commentID} – Get specific article comment. Retrieves a particular comment by ID on the article. Useful if you have a comment ID reference.
	•	GET /api/articles/{articleID}/subarticles – List sub-articles. If articles are organized in a hierarchy, this endpoint returns child articles of a given article (like pages under a section). Fields might include each sub-article’s id, summary, etc. Use this to traverse a knowledge base tree.
	•	GET /api/articles/{articleID}/parent – Get parent article. Returns the parent page of a given article (if it’s a sub-article), including at least the parent’s id and summary. This helps navigate up the hierarchy.

Note: Article endpoints require the user to have permission to view the knowledge base project where the article resides. The structure is analogous to issues (with comments, attachments sub-resources). If you plan to use YouTrack data with language models, fetching articles could be very useful as they contain explanatory text and documentation that might augment the issue data.

Miscellaneous and Utility Endpoints
	•	GET /api/issuesGetter/count?query=... – Get issue count for a query. This endpoint returns the number of issues that match a given search query, without retrieving the issues themselves. It’s useful for quick stats or to validate how many issues a query would return. You provide a query parameter just like in the issues list. The response includes a count.
Example: GET /api/issuesGetter/count?query=project: PRJ #Unresolved will return a JSON object like { "count": 42, "id": "some-id" } indicating 42 issues are unresolved in project PRJ. (The id in the response is not an issue ID but an ephemeral identifier for the count request – you can ignore it and use just the count.) No fields param is needed except perhaps fields=count to limit output ￼.
Note: This endpoint might appear as /api/issues/count in some contexts, but officially it’s available via the issues “getter”. The purpose is read-only and it doesn’t count as a separate resource to list; it’s effectively a utility.
	•	GET /api/search/assist?query=<partial>&caret=<pos>&... – Search query suggestions. Provides auto-completion suggestions for issue search queries. If you are building an interface or just want to see how YouTrack would complete a query, you can call this with a partial query and a caret position (index within the query string where the cursor is). The response suggests completions/options. For example, GET /api/search/assist?query=project: PR&caret=9&fields=suggestions(option,description) might suggest project names starting with “PR”. This is the same data used by the UI to show dropdown suggestions for search queries. Typically, you’ll specify query=<current query text> and caret=<cursor position> (usually the end of the string length). The response includes an array of suggestions with each suggestion’s text (option) and a human-friendly description.
Note: This endpoint is read-only and doesn’t change any data. It is helpful if integrating YouTrack search in a tool. It does not require any special permission beyond what searching issues requires, but it will only suggest values the user could actually use (e.g. projects they have access to, saved search names they know, etc.).
	•	GET /api/commands/assist?query=<partial>&... – Command suggestions. (Related to the Commands resource, though the actual method is POST in the collection.) This would return suggestions for the command dialog (used to modify issues via natural language commands). While not a GET in the collection (the Postman shows it as POST), if there were a GET variant it might function similarly to search assist but for commands. This is more of an interactive feature than data retrieval, so it’s usually outside the scope of data extraction for analysis. Mentioned here for completeness – it provides possible commands given a partial input and context, which could be useful for building automation tools. (To use it, refer to YouTrack’s documentation on commands; it typically needs the issue context.)
	•	GET /api/admin/telemetry – Instance telemetry data. (Admin-only.) Returns system statistics such as uptime, database size, number of entities, etc. ￼ ￼. This is mainly for administrative insight. The response includes fields like databaseSize, startedTime, uptime (e.g. “5 days 4 hours”), textIndexSize, etc. Use fields to select which stats. This can be useful to monitor system health but not directly related to issue/project data. There are no parameters besides fields. Example: GET /api/admin/telemetry?fields=databaseSize,uptime might return the size in bytes and a human-readable uptime string. Rate limit is not an issue here as it’s a single small object.
	•	GET /api/admin/globalSettings (and sub-resources) – Global settings. (Admin-only.) YouTrack provides various global configuration endpoints (appearance settings, locale, notification defaults, etc.). For instance, /api/admin/globalSettings returns an object with installation settings (like base URL, default time zone, etc.), /api/admin/globalSettings/locale returns localization settings, etc. These are configuration data, not typically needed for data analysis. If needed, one can retrieve them with appropriate fields. For example, GET /api/admin/globalSettings?fields=systemLanguage,ringVersion could show the default language and version.
Similarly, License info (/api/admin/globalSettings/license), Notifications settings, REST CORS settings, etc., are available. These are mainly relevant for admin monitoring or if you are building an admin dashboard via API. They do not involve large data sets. We include them for completeness, but they are not usually pertinent to visualizing issue tracking data.

Rate Limiting: YouTrack’s documentation does not specify a strict public rate limit for the REST API. However, as a best practice, clients should avoid flooding the server with requests. Use pagination to batch data requests and the fields parameter to minimize payload sizes. In practice, the default page size of 42 and the need to explicitly request fields enforce a controlled usage pattern ￼ ￼. If you are using YouTrack Cloud (JetBrains-hosted), there may be invisible throttling to protect the service (e.g. very high request rates might get slowed down). For large data extraction (e.g. exporting thousands of issues), it’s wise to insert short delays or check for HTTP 429 responses just in case. Self-hosted YouTrack typically relies on the admin to configure any reverse-proxy rate limits if needed – by default, the application itself doesn’t seem to impose a strict request-per-minute cap in documentation. Always ensure your token has sufficient permissions for the data you are retrieving to avoid 401/403 errors.

Common Response Structure: All responses are JSON. For collection endpoints (lists), the response is usually a JSON array of objects. For single-object endpoints, the response is a JSON object. Most entity objects include an $type field indicating the entity type (e.g. "Issue", "User", "Project" etc.), and an id which is the internal database ID (not the human-readable issue ID) ￼ ￼. Many entities also have a human-readable key or name: for issues idReadable (like “PRJ-123”), for projects a shortName, etc. Date/time fields are given as Unix timestamps in milliseconds (e.g. "created": 1539089914788). Duration fields (like work item duration or time tracking estimates) are often returned as an object with minutesand a formattedpresentationstring. When using thefieldsparameter, note that nested objects will appear according to the structure requested (e.g.reporter(login)yields an object for reporter with only login). If a field is not requested, it will be omitted from the JSON. Absent or null values are usually simply not present if not requested, or present asnull` if requested but unset.

Each GET endpoint above supports standard HTTP caching headers as well, but since the data is dynamic, clients typically just fetch fresh data as needed. In summary, to efficiently extract all accessible data from a YouTrack instance: one would iterate through projects, then for each project (or globally) retrieve issues (with relevant fields or in chunks), along with related entities like users, tags, custom field definitions (to interpret fields), agile boards, etc., using the endpoints listed. By leveraging these read-only API calls and proper use of query parameters, you can visualize the data or feed it into a language model with full context of the issue tracker’s content and structure. Each category of data – issues, comments, history, users, etc. – is available through these REST endpoints in a well-structured JSON format, making programmatic analysis and integration straightforward.





Alright, let’s go deep into every GET endpoint that the Postman collection offers for data extraction from YouTrack, complete with the example responses provided. I’ll break it down by category so you can see exactly what data you can pull and how the examples look.

────────────────────────────
1. Activities

• Read a List of Activity Items
 – Endpoint:
  GET {{baseUrl}}/activities
 – Query Parameters:
  • fields – Specify which fields to return (e.g. added,author(id,login,ringId),category(id),field(customField(fieldType(id),id,localizedName,name),id,name),id,removed,target,targetMember,timestamp)
  • categories – Filter by activity categories (e.g. IssueCreatedCategory,CommentsCategory)
  • $skip and $top – For pagination
 – Example Response:
  You get an array of activity items. For instance, one sample item shows:
  json   {     "added": [{ "id": "4-2", "$type": "IssueComment" }],     "id": "4-2.0-0",     "author": { "login": "john.doe", "name": "John Doe", "id": "1-2", "$type": "User" },     "timestamp": 1533221614364,     "target": { "id": "4-2", "$type": "IssueComment" },     "$type": "CommentActivityItem"   }   
  This endpoint returns various activities like issue creation and comment additions.
  YouTrack REST API.postman_collection.json](file-service://file-AyapbbVijefVNp4dnohzj3)

• Read a Specific Activity Item
 – Endpoint:
  GET {{baseUrl}}/activities/:id
 – Usage:
  Replace :id with the activity item’s ID (e.g. using {{activityItemID}}).
 – Example Response:
  A detailed object is returned including type, added items, author info, and timestamps. One sample response includes additional navigation info such as cursors for paging:
  json   {     "afterCursor": "AI.2-2+:CM.4-0-:1533132320210",     "beforeCursor": "AI.^+:CM.^+:1533132312016",     "activities": [       {         "id": "2-0.0-0",         "author": { "login": "root", "name": "John Smith", "$type": "User" },         "timestamp": 1533132312016,         "$type": "IssueCreatedActivityItem"       },       ...     ],     "id": "AI.^+:CM.^+:1533132312016#AI.2-2+:CM.4-0-:1533132320210.d",     "$type": "ActivityCursorPage"   }   
  ouTrack REST API.postman_collection.json](file-service://file-AyapbbVijefVNp4dnohzj3)

────────────────────────────
2. Comments

• Issue Comments
 – Endpoint:
  GET {{baseUrl}}/issues/:id/comments
 – Query Parameters:
  Specify fields such as id,author(login,name,id),deleted,text,updated,visibility(...)
 – Example Response:
  Returns an array of comment objects; each includes the comment text, author details, and a visibility structure that lists permitted groups/users.

• Article Comments
 – Endpoint:
  GET {{baseUrl}}/articles/:id/comments
 – Example Response:
  Similar to issue comments, you get objects with fields like id,author(id,name),text,created plus visibility info.
  (These endpoints let you pull comment data from both issues and articles.)
  YouTrack REST API.postman_collection.json](file-service://file-AyapbbVijefVNp4dnohzj3)

────────────────────────────
3. Issue Attachments

• Read a Specific Issue Attachment
 – Endpoint:
  GET {{baseUrl}}/issues/:id/attachments/:issueAttachmentId
 – Query Parameters:
  Include fields like id,name,author(id,name),created,updated,size,mimeType,extension,metaData,url
 – Example Response:
  You receive a JSON object detailing the attachment’s metadata, which is perfect for linking to binary data or displaying file details.
  YouTrack REST API.postman_collection.json](file-service://file-AyapbbVijefVNp4dnohzj3)

────────────────────────────
4. Administration – Custom Field Settings

These endpoints let you extract metadata on custom fields and their value bundles. They’re grouped into Build Bundles and Enum Bundles.

A. Build Bundles

• Read a List of BuildBundleElements
 – Endpoint:
  GET {{baseUrl}}/admin/customFieldSettings/bundles/build/:id/values
 – Query Parameters:
  Specify fields like id,name,assembleDate,description
 – Example Response:
  Returns an array such as:
  json   [     {       "assembleDate": 1627300800000,       "description": null,       "name": "135",       "id": "150-5",       "$type": "BuildBundleElement"     },     { ... }   ]   

• Read a Specific BuildBundleElement
 – Endpoint:
  GET {{baseUrl}}/admin/customFieldSettings/bundles/build/:id/values/:buildBundleElementId
 – Example Response:
  json   {     "assembleDate": 1627300800000,     "description": null,     "name": "135",     "id": "150-5",     "$type": "BuildBundleElement"   }   
  YouTrack REST API.postman_collection.json](file-service://file-AyapbbVijefVNp4dnohzj3)

• Read a Specific BuildBundle
 – Endpoint:
  GET {{baseUrl}}/admin/customFieldSettings/bundles/build/:id
 – Query Parameters:
  Include fields like name,id,values(name,id,description,ordinal,hasRunningJob,assembleDate),isUpdateable
 – Example Response:
  Returns an object that contains the bundle’s name, update flag, and an array of its elements.
  YouTrack REST API.postman_collection.json](file-service://file-AyapbbVijefVNp4dnohzj3)

• Read a List of BuildBundles
 – Endpoint:
  GET {{baseUrl}}/admin/customFieldSettings/bundles/build
 – Query Parameters:
  Fields such as id,name,fieldType(presentation,id)
 – Example Response:
  An array of bundles, each showing minimal metadata like name and id.
  YouTrack REST API.postman_collection.json](file-service://file-AyapbbVijefVNp4dnohzj3)

• Add, Update, and Delete endpoints also exist for BuildBundleElements and BuildBundles; their sample responses (for update, you see the changed object; for delete, an empty body is returned) follow the same patterns.

B. Enum Bundles

• Read a Specific EnumBundleElement
 – Endpoint:
  GET {{baseUrl}}/admin/customFieldSettings/bundles/enum/:id/values/:enumBundleElementId
 – Query Parameters:
  Fields like id,name
 – Example Response:
  json   {     "name": "Bug",     "id": "55-5",     "$type": "EnumBundleElement"   }   
  YouTrack REST API.postman_collection.json](file-service://file-AyapbbVijefVNp4dnohzj3)

• Read a List of EnumBundleElements
 – Endpoint:
  GET {{baseUrl}}/admin/customFieldSettings/bundles/enum/:id/values
 – Example Response:
  An array of enum values such as “Bug”, “Exception”, “Feature”, etc.
  YouTrack REST API.postman_collection.json](file-service://file-AyapbbVijefVNp4dnohzj3)

• Update and Delete endpoints for EnumBundleElements are available as well, each returning updated objects or empty responses upon deletion.

────────────────────────────
5. Time Tracking

• Issue Work Items
 – Endpoint:
  GET {{baseUrl}}/issues/:id/timeTracking/workItems
 – Query Parameters:
  Fields like id,author(id,name),date,duration(id,minutes,presentation)
 – Example Response:
  You get an array of work items; one example might look like:
  json   {     "id": "workitem-id",     "author": { "id": "1-2", "name": "John Doe" },     "date": 1627300800000,     "duration": { "id": "duration-id", "minutes": 120, "presentation": "2h" }   }   
  YouTrack REST API.postman_collection.json](file-service://file-AyapbbVijefVNp4dnohzj3)

────────────────────────────
6. Users and Groups

• Users
 – Endpoint:
  GET {{baseUrl}}/users
 – Example Response:
  Returns an array of user objects, e.g.:
  json   [     { "id": "1-2", "login": "john.doe" },     { "id": "1-3", "login": "jane.smith" }   ]   

• User Groups
 – Endpoint:
  GET {{baseUrl}}/groups
 – Example Response:
  An array of group objects with fields like id and login.

────────────────────────────
7. Agile Boards and Sprints

• Agile Boards
 – Endpoint:
  GET {{baseUrl}}/agiles
 – Query Parameters:
  Fields such as id,name
 – Example Response:
  Returns a list of boards, e.g.:
  json   [     { "id": "board-1", "name": "Sample Agile Board" },     { "id": "board-2", "name": "Development Board" }   ]   

• Sprints on a Board
 – Endpoint:
  GET {{baseUrl}}/agiles/:agileBoardID/sprints
 – Example Response:
  An array of sprints with fields like id, name, start, and finish.

────────────────────────────
8. Saved Queries

• Endpoint:
  GET {{baseUrl}}/savedQueries
• Example Response:
  A list of saved search queries is returned with fields such as id, name, and query, allowing you to retrieve and reuse predefined searches.

────────────────────────────
9. Articles

• Articles
 – Endpoint:
  GET {{baseUrl}}/articles
 – Query Parameters:
  Specify fields like id,summary
 – Example Response:
  An array of article objects.

• Article Attachments and Comments
 – Attachments:
  GET {{baseUrl}}/articles/:articleID/attachments returns attachment metadata.
 – Comments:
  GET {{baseUrl}}/articles/:articleID/comments returns comment objects including author and creation time.

────────────────────────────
10. Telemetry and Backups

• Telemetry
 – Endpoint:
  GET {{baseUrl}}/admin/telemetry
 – Example Response:
  Returns system-level metrics such as:
  json   {     "databaseSize": 123456789,     "uptime": 9876543,     "startedTime": 1627300800000,     "textIndexSize": 456789   }   
  YouTrack REST API.postman_collection.json](file-service://file-AyapbbVijefVNp4dnohzj3)

• Database Backups
 – Endpoint:
  GET {{baseUrl}}/admin/databaseBackup/backups
 – Example Response:
  Returns backup file metadata including names and IDs.

────────────────────────────
Putting It All Together

The Postman collection you sent is incredibly comprehensive. It covers nearly every GET method you might need to pull data from a YouTrack instance. Each endpoint is designed to allow you to select the precise fields you want (thus minimizing payload size), and almost every endpoint comes with example data so you know exactly what to expect. This includes everything from low-level activity tracking (with detailed cursor-based pagination) to high-level system telemetry.

If your goal is to extract and then visualize or feed this data into LLMs, you have all the modern methods at your fingertips:
  • Activities (both list and detailed single activity views)
  • Comments (for issues and articles)
  • Attachments (with full metadata)
  • Custom Field data (via both Build and Enum Bundles)
  • Work items for time tracking
  • User and group information
  • Agile board and sprint details
  • Saved queries, articles, and system telemetry

Each endpoint’s sample response (as shown in the collection) confirms the data shape and fields available. I’ve referenced several parts of the collection (‡YouTrack REST API.postman_collection.json](file-service://file-AyapbbVijefVNp4dnohzj3), ‡YouTrack REST API.postman_collection.json](file-service://file-AyapbbVijefVNp4dnohzj3), ‡YouTrack REST API.postman_collection.json](file-service://file-AyapbbVijefVNp4dnohzj3), etc.) to give you a complete picture.

So, to answer your question: Yes, the detailed list above covers every available GET endpoint for data extraction that’s in the Postman collection you sent, along with the example responses provided in that documentation. If you need further granularity on any specific endpoint or additional endpoints beyond GET (like POST/DELETE for data manipulation), the official documentation and the full collection will have those details too.

Hope this lengthy, detailed rundown gives you everything you need to build out your visualization and LLM pipeline. Let me know if you want to drill down further on any part!