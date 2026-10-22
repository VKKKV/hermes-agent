"""Slash command dispatch remains functional without recording usage."""
from cli import HermesCLI

def test_alias_dispatch_does_not_need_a_metrics_subscriber(monkeypatch):
    ran=[]
    monkeypatch.setattr(HermesCLI,"_cmd_new",lambda self,cmd:ran.append(cmd))
    cli=object.__new__(HermesCLI)
    cli.config={"quick_commands":{"rs":{"type":"alias","target":"/reset"}}}
    cli.process_command("/reset");cli.process_command("/rs")
    assert ran==["/reset","/reset"]
