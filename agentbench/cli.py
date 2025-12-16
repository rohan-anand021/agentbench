import typer
from pathlib import Path
from agentbench.run_task import run_task

app = typer.Typer(no_args_is_help = True)

@app.command('run-task')
def run_task_cmd(task: Path, out: Path = Path('artifacts')):
    path = run_task(task, out)
    typer.echo(f'Path: {path}')

@app.callback()
def main():
    """
    AgentBench CLI
    """
    pass
