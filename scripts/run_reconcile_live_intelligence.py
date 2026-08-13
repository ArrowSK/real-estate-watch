from pathlib import Path

script = Path("scripts/reconcile_live_intelligence.py").read_text()
old = 'A megfigyelt kínálati adatok még nem érték el az ehhez a választáshoz szükséges minimális közölhető mintát.'
new = 'A megfigyelt kínálati adatok még nem érték el a közölhető minimális mintát ehhez a választáshoz.'
if script.count(old) != 1:
    raise SystemExit(f"Expected exactly one outdated Hungarian anchor, found {script.count(old)}")
script = script.replace(old, new, 1)
exec(compile(script, "scripts/reconcile_live_intelligence.py", "exec"))
