# AI Collaboration Guidance

Patterns for effective collaboration with AI coding assistants.

---

## 1. Context Setting

### Start Sessions with Context
Before diving into code, provide:
- **Project overview**: What does this codebase do?
- **Current state**: What's already built? What patterns exist?
- **Task scope**: What specifically are we working on?
- **Constraints**: What should we avoid changing?

### Reference Existing Guidance
```
Before we start, please review:
- CODING-GUIDANCE.md for architectural patterns
- The REVIEW_*.md files for package-specific context
- Current sprint goals in work-index.yaml
```

### Use `work focus` Pattern
When using WorkSync:
1. `work status` - See what's active
2. `work focus STORY-X` - Load story context
3. Work with full context available

---

## 2. Prompting Patterns

### Be Specific About Output
```
# Vague
Fix the authentication bug.

# Specific
Fix the authentication bug where users are logged out after 5 minutes.
- The issue is in src/auth/session.ts
- We use JWT with refresh tokens
- Don't change the token expiry, fix the refresh logic
```

### Request Incremental Changes
```
# Overwhelming
Refactor the entire auth system to use OAuth.

# Incremental
Let's plan the OAuth migration:
1. First, show me what files would need to change
2. Then let's update the auth service interface
3. Then implement the OAuth provider
```

### Ask for Explanations
```
Before implementing, explain:
- Why this approach over alternatives?
- What are the tradeoffs?
- What could go wrong?
```

---

## 3. Code Review Mode

### Use AI as Reviewer
```
Review this PR for:
- Violations of our thin CLI / thick services pattern
- Missing error handling
- Test coverage gaps
- Security concerns

Reference CODING-GUIDANCE.md for our standards.
```

### Request Specific Checks
```
Check this code against:
- [ ] No business logic in CLI layer
- [ ] All errors handled explicitly
- [ ] Context passed to external calls
- [ ] Tests cover happy path and error path
```

---

## 4. Documentation of Decisions

### Capture Reasoning
When AI suggests an approach, document why:
```go
// Using retry with exponential backoff here because:
// - AWS SSM can have transient failures
// - We discussed this pattern for all AWS calls
// - See STORY-5 notes for context
```

### Track Deferred Work
```
# In story notes:
Known gaps / follow-ups:
- [ ] Error handling for edge case X (deferred to STORY-10)
- [ ] Additional test coverage for path Y
```

### Update Guidance When Patterns Emerge
If you and AI discover a better pattern:
1. Implement it in current task
2. Update CODING-GUIDANCE.md
3. Note it for future reference

---

## 5. Quality Gates

### Before Accepting AI Code
- [ ] Does it follow project architecture?
- [ ] Are errors handled properly?
- [ ] Is it testable? Are tests included?
- [ ] Does it introduce duplication?
- [ ] Would a new developer understand it?

### Red Flags to Catch
- Silent error ignoring (`catch {}`, `_ = err`)
- Business logic in wrong layer
- Hardcoded values that should be config
- Missing context in async operations
- Copy-pasted code instead of shared helpers

### Ask AI to Self-Review
```
Before we commit, review your changes against:
- Our architectural guardrails
- The patterns in existing code
- Test coverage expectations

Flag anything that deviates.
```

---

## 6. Session Handoff

### End-of-Session Summary
Ask AI to summarize:
```
Summarize what we accomplished:
- What was changed
- What decisions were made and why
- What's left to do
- Any concerns or follow-ups
```

### Update Work Tracking
1. Mark story status in work-index.yaml
2. Add notes about what was done
3. Document known gaps
4. `work sync` to update Obsidian

### Context for Next Session
```
At end of session, capture:
- Current state of the work
- Next logical step
- Any blockers or questions
- Files that were modified
```

---

## 7. Prompt Templates

### New Feature
```
I need to implement [feature description].

Context:
- This is for [project name]
- It should follow our [thin CLI / service layer] pattern
- Related code is in [paths]

Requirements:
- [Specific requirements]

Constraints:
- Don't change [existing behavior]
- Follow patterns in [reference file]

Please:
1. Outline the approach first
2. Identify files to create/modify
3. Then implement incrementally
```

### Bug Fix
```
Bug: [Description of the bug]
Expected: [What should happen]
Actual: [What happens instead]

Relevant files:
- [file paths]

Please:
1. Analyze the root cause
2. Propose a fix
3. Add a test that would have caught this
4. Implement the fix
```

### Code Review
```
Please review the following code against our standards:

[code or file path]

Check for:
- Architecture violations (see CODING-GUIDANCE.md)
- Error handling issues
- Test coverage gaps
- Security concerns
- Code quality / readability

Format as: Issue | Severity | Recommendation
```
