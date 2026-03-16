import os
import json
import glob
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich import print as rprint

console = Console()

def get_latest_logs(limit=5):
    log_files = glob.glob("logs/payload_logs/*.json")
    if not log_files:
        return []
    
    # Group by request_id
    sessions = {}
    for f in log_files:
        base = os.path.basename(f)
        request_id = base.split('_')[0]
        if request_id not in sessions:
            sessions[request_id] = []
        sessions[request_id].append(f)
    
    # Sort request IDs by modification time of their files
    sorted_ids = sorted(sessions.keys(), key=lambda x: os.path.getmtime(sessions[x][0]), reverse=True)
    return sorted_ids[:limit], sessions

def view_logs():
    result = get_latest_logs()
    if not result:
        rprint("[bold yellow]No logs found in payload_logs/[/bold yellow]")
        return
    
    ids, sessions = result

    rprint(f"[bold blue]Showing last {len(ids)} request sessions:[/bold blue]\n")

    for req_id in ids:
        # Sort files in session by stage
        files = sorted(sessions[req_id])
        
        table = Table(title=f"Request ID: {req_id}", show_header=True, header_style="bold magenta")
        table.add_column("Stage", style="dim")
        table.add_column("Direction", style="cyan")
        table.add_column("Content Summary", style="white")

        for f in files:
            with open(f, "r") as log_f:
                data = json.load(log_f)
                direction = data.get("direction", "Unknown")
                
                # Summary logic
                if "messages" in data:
                    content = f"Messages: {len(data['messages'])} (Last: {data['messages'][-1].get('content', '')[:50]}...)"
                elif "response" in data:
                    res = data["response"]
                    if isinstance(res, dict) and "choices" in res:
                        content = f"Response: {res['choices'][0]['message']['content'][:50]}..."
                    else:
                        content = "Response received"
                elif "error" in data:
                    content = f"[red]Error: {data['error'][:100]}[/red]"
                else:
                    content = "Detailed payload"

                stage_name = os.path.basename(f).split('_')[1]
                table.add_row(stage_name, direction, content)

        console.print(table)
        
        # Optionally show full details for the very last one
        if req_id == ids[0]:
            rprint("\n[bold green]--- Latest Session Detail ---[/bold green]")
            for f in files:
                with open(f, "r") as log_f:
                    data = json.load(log_f)
                    title = f"File: {os.path.basename(f)} | {data.get('direction')}"
                    json_str = json.dumps(data, indent=2)
                    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
                    console.print(Panel(syntax, title=title, expand=False))
            rprint("-" * 50)

if __name__ == "__main__":
    view_logs()
