---
name: rule-engine
description: Use this Skill every time you need to change something in the rule engine logic.
---

# Instructions

When changing logic in the rule engine you need to:

- Update the schema file in `rules.schema.json`
- Create or update code-rule tests for the use case. (read bellow how these tests work)
- Update the rules documentation in `docs/rules.md` if necessary.



## Test files

The rules test logic is in `tests/rules`. For each test there is a folder with 3 files:
- `rules.yml`: the rules to be applied to the file
- `input.[ext]`: the file to be evaluated by the rules (extension changes based on the file type )
- `outcome.[ext]`: the expected output after the rules are applied (extension changes based on the file type )

There is logic already to run these tests, you just need to follow the same structure, create the rule that you need to test and sample files to validate that the rule is working as expected.

To run the tests just run `task test-rules` in the terminal. This will run all the tests in `tests/rules` and validate that the outcome is the expected one.
