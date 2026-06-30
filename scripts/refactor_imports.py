import os

def replace_in_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    new_content = content
    # Handle core
    new_content = new_content.replace('from visor.core.', 'from visor.core.')
    new_content = new_content.replace('from visor.core ', 'from visor.core ')
    new_content = new_content.replace('import visor.core.', 'import visor.core.')
    new_content = new_content.replace('import core\n', 'import visor.core\n')
    
    # Handle strategy
    new_content = new_content.replace('from visor.strategy.', 'from visor.strategy.')
    new_content = new_content.replace('from visor.strategy ', 'from visor.strategy ')
    new_content = new_content.replace('import visor.strategy.', 'import visor.strategy.')
    new_content = new_content.replace('import strategy\n', 'import visor.strategy\n')

    # Handle platforms
    new_content = new_content.replace('from visor.platforms.', 'from visor.platforms.')
    new_content = new_content.replace('from visor.platforms ', 'from visor.platforms ')
    new_content = new_content.replace('import visor.platforms.', 'import visor.platforms.')
    new_content = new_content.replace('import platforms\n', 'import visor.platforms\n')

    if content != new_content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        print(f"Updated {filepath}")

for root, _, files in os.walk('.'):
    for f in files:
        if f.endswith('.py'):
            replace_in_file(os.path.join(root, f))
