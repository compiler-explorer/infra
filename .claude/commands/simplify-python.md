Simplify and refactor Python code in @$ARGUMENTS following these steps:

## Instructions
Work through each function methodically, simplifying where it improves readability and reduces complexity and nesting. Create a todo list to track each function and run tests/linter after each change.

## Examples of Simplification
1. **Exception handling**:
   - Catch exceptions as locally as possible to reduce indentation
   - Use `RuntimeError` instead of generic `Exception`
   - Remove unnecessary try/except wrapping

Good:
```py
try:
  bob = do_thing_that_might_throw()
except RuntimeError:
  LOGGER.error(...)
  raise
if bob:
  return 123
do_other_thing()
return 0
```

Bad:
```py
try:
  bob = do_thing_that_might_throw()
  # bad - could be ouside of the exception handler
  if bob:
    return 123
  else: # bad, no need for else after a return
    do_other_thing()
    return 0
except Exception: # Bad - catching Exception
  LOGGER.error(...)
  raise
```

2. **Control flow**:
   - Remove `else` after `return`, `raise`, or `continue`
   - Use early returns to reduce nesting
   - Convert `elif` to `if` after returns

3. **Comments**:
   - Remove obvious comments that describe what code does.
   - KEEP comments that explain WHY or non-obvious behavior
   - KEEP comments about data structure formats or magic numbers

Good (explains why):
```py
# We have to sync now to ensure consistency, see documentation for details.
fs.sync()
```

Bad (obvious from naming):
```py
# Move the file
file.move()
```

4. **Python idioms**:
   - Use list/dict comprehensions where they improve readability
   - Use modern python like `match` and walrus operator
   - Simplify variable assignments (avoid unnecessary intermediates, except to avoid putting expressions in f-strings)

5. **Code duplication**:
   - Extract duplicated logic ONLY if substantial (>20 lines)
   - Verify extracted functions preserve exact behavior
   - Get review from python-code-reviewer for any extractions

## Process
1. Create a todo list tracking each function to simplify
2. For each function:
   - Apply simplification rules
   - Run `uv run pytest <test_file> -v` after changes
   - Run `make static-checks` after changes
   - If tests fail or linter complains, STOP and discuss
3. After all functions, run full test suite: `make test`
4. Run final linter check: `make static-checks`
5. Commit with descriptive message about simplifications made

## What NOT to do
- Don't add new functions unless eliminating significant duplication
- Don't remove helpful comments (data formats, reasons, edge cases)
- Don't change behavior - simplification should be refactoring only
- Don't disable linter rules - fix the issues properly

## Testing Requirements
- Run tests after EACH function change
- Run linter after EACH function change
- If anything fails, stop immediately
- Never commit without all tests passing
