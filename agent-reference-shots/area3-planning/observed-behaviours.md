# Claude Code 2.1.306 - Area 3 observed behaviours
# Captured 2026-10-21T17:58:20Z on win32-x64

### 1. Plan mode headless run blocks the file write
$ claude -p --permission-mode plan 'Create a file called demo-plan.txt containing exactly the text: hello plan' --output-format=json

Observed: result said plan written to C:\Users\Admin\.claude\plans\create-a-file-called-jaunty-shell.md; ExitPlanMode and AskUserQuestion NOT in session tool list; demo-plan.txt was NOT created.

### 2. Subagent delegation stats
$ claude -p 'Use the Explore subagent ...' --output-format=json
subagent_stats: {"spawned":1,"requested":{"background":0,"foreground":0,"unset":1},"started_in_background":1,"max_depth":1,"spawned_by_subagents":0,"completed":1,"failed":0,"killed":{...0},"refused":{"depth_limit":0,"concurrency_limit":0,"budget":0},"by_type":{"Explore":1}}

### 3. Task tracking tool availability gating
$ claude -p 'Output ONLY the tool names available to you'
default session  -> Agent, Bash, Cron*, DesignSync, Edit, EnterWorktree, ExitWorktree, Glob, Grep, ListAgents, Monitor, NotebookEdit, PowerShell, PushNotification, Read, ReportFindings, ScheduleWakeup, SendMessage, Skill, TaskStop, ToolSearch, Workflow, Write + mcp__*
  (no TodoWrite/TaskCreate/TaskGet/TaskList/TaskUpdate)
$ CLAUDE_CODE_ENABLE_TODO_TOOLS=1 claude -p '...'
  -> TaskCreate, TaskGet, TaskList, TaskUpdate present

### 4. Built-in subagent types reported by the model
Agent, claude, Explore, general-purpose, Plan, statusline-setup
