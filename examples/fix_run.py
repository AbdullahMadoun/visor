import re

with open('run.py', 'r') as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if line.strip().startswith('elif args.flow == "mind2web_task_'):
        skip = True
        continue
    if skip and line.strip().startswith('from visor.platforms.mind2web'):
        continue
    if skip and not line.strip().startswith('from visor.platforms.mind2web') and not line.strip().startswith('elif args.flow == "mind2web_task_'):
        skip = False
    if not skip:
        if line.strip() == 'else:':
            # Insert the new tasks before else
            for i in range(20, 40):
                new_lines.append(f'    elif args.flow == "mind2web_task_{i}":\n')
                new_lines.append(f'        from visor.platforms.mind2web.task_{i} import run_task as flow_fn\n')
            
            # Since my_worker.py appended 80 to 99 previously, maybe let's just make sure there's an else:
            new_lines.append('    else:\n')
        elif line.strip() == 'elif args.flow == "mind2web_task_80":':
            pass # already skipped
        else:
            new_lines.append(line)

with open('run.py', 'w') as f:
    f.writelines(new_lines)
