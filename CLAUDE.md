# Instructions

This project is a simple service that monitors changes on files based on rules and applies actions accordingly. The idea is to allow to enforce specific rules to files, like config files.
For example, if an mcp.json file sets some mcp servers that are not allowed by the organization, a rule can detect that mcp config and remove it.

Project uses `uv` for managing dependencies and taskfile to manage tasks/scripts.


## Useful commands

- `uv sync` to install dependencies
- `task test` to run all tests
- `task test:rules` to run only the rules tests

## Coding instructions

- Always use guarded clauses, also known as early returns, to reduce nesting and improve readability. For example, instead of:
- DRY (Don't Repeat Yourself): If you are checking the same file path in five different places, move that path to a single variable at the top.
- The "Fail Fast" Principle. Similar to Guard Clauses, your code should crash or exit immediately if a critical resource is missing.
