# General Coding Guidance

Universal practices that apply across all projects and languages.

---

## 1. Code Organization

### Single Responsibility
- Functions should do one thing well
- Files should have a clear, focused purpose
- Modules/packages should represent cohesive concepts

### Layered Architecture
- **Thin adapters, thick core**: CLI/API layers parse input and call services; business logic lives in services
- **Dependency direction**: Core logic should not depend on I/O or framework specifics
- **Clear boundaries**: Define explicit interfaces between layers

### Avoid Duplication
- Extract shared logic into helpers when patterns repeat 3+ times
- Parameterize behavior instead of copy-pasting with minor variations
- Document where shared helpers live so future developers find them

---

## 2. Error Handling

### Be Explicit
```
# Good: Clear error handling
result, err := operation()
if err != nil {
    return fmt.Errorf("operation failed: %w", err)
}

# Bad: Silent failure
result, _ := operation()
```

### Surface Failures
- If an operation can fail in a way the user cares about, surface it clearly
- Never silently ignore: file I/O, network calls, JSON encoding, external commands
- Provide actionable error messages with context

### Fail Fast
- Validate inputs early, before expensive operations
- Return errors rather than continuing with bad state
- Use clear exit codes in CLI applications

---

## 3. Testing Strategy

### Test Pyramid
- **Unit tests**: Fast, focused, test single functions/methods
- **Integration tests**: Test component interactions with real (or stubbed) dependencies
- **E2E tests**: Minimal, test critical user paths

### Testability Patterns
- Inject dependencies rather than hardcoding them
- Use interfaces/seams for external calls (DB, HTTP, shell commands)
- Keep tests deterministic - no real network calls, no time-dependent behavior

### Test Coverage Goals
- Aim for meaningful coverage, not percentage theater
- Cover: happy paths, error paths, edge cases
- Every new behavior should have a focused test

---

## 4. Documentation

### Code Comments
- Explain *why*, not *what* (code shows what)
- Document non-obvious decisions and constraints
- Keep comments updated when code changes

### README/Docs
- Quick start should work in < 5 minutes
- Document prerequisites and environment setup
- Include common troubleshooting scenarios

### Known Gaps
- When deferring work, document it explicitly
- Prefer unchecked checkboxes over "we'll remember later"
- Link to tracking issues/stories for follow-up work

---

## 5. Version Control

### Commit Hygiene
- Atomic commits: one logical change per commit
- Clear commit messages: imperative mood, explain why
- Don't commit: secrets, large binaries, generated files

### Branch Strategy
- Keep branches short-lived
- Rebase/squash for clean history before merge
- Delete branches after merge

---

## 6. Security Defaults

### Input Validation
- Validate at system boundaries (user input, external APIs)
- Sanitize before shell execution or SQL queries
- Use parameterized queries, never string concatenation

### Secrets Management
- Never hardcode secrets in source code
- Use environment variables or secret stores
- Rotate credentials regularly

### Principle of Least Privilege
- Request minimal permissions needed
- Scope access tokens narrowly
- Audit access patterns

---

## AI Collaboration Note

When working with AI assistants on this codebase:
- Reference this guidance to maintain consistency
- Ask the AI to explain deviations from these patterns
- Use the AI to help identify violations in code reviews
