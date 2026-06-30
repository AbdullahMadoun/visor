import re

with open("run.py", "r") as f:
    content = f.read()

# Insert the mind2web flow handling if not exists
if "mind2web_task_" not in content:
    replacement = """    elif args.flow.startswith("mind2web_task_"):
        task_idx = args.flow.split("_")[-1]
        exec(f"from visor.platforms.mind2web.task_{task_idx} import run_task as flow_fn")
    else:"""
    content = content.replace("    else:", replacement)

with open("run.py", "w") as f:
    f.write(content)
