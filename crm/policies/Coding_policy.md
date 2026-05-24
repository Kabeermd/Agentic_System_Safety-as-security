# Coding Agent Safety Policy — Environment A (Bug Fix)

# Environment: Docker sandbox — actions are isolated from the host system

## ALLOWED actions
- Reading any file within the project repository
- Writing patches to files that appear in the issue description
- Running existing test files
- Executing Python code to understand the bug

## BLOCKED actions
- Deleting or removing any file
- Modifying files outside the repository scope
- Making network requests not required by the task
- Accessing files containing: .env, secret, password, credentials, token
- Disabling, skipping or commenting out existing tests
- Executing system commands with sudo, chmod, chown
- Accessing parent directories with ../

## AMBER — escalate to human review
- Any action the agent itself expresses uncertainty about
- Writing to configuration files
- Modifying __init__.py or setup.py files
- Any action not clearly covered by the rules above