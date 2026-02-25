# Go Coding Guidance

Go-specific patterns and practices for maintainable codebases.

---

## 1. Package Structure

### Standard Layout
```
cmd/
  myapp/
    main.go           # Entry point, minimal logic
internal/
  cli/                # CLI adapters (thin)
  services/           # Business logic (thick)
  transport/          # External integrations
pkg/
  api/
    types/            # Shared request/response types
    validate/         # Validation helpers
```

### Package Responsibilities
- `cmd/`: Parse args, wire dependencies, call internal packages
- `internal/cli/`: Flag parsing, request construction, output formatting
- `internal/services/`: Business logic, orchestration, error handling
- `internal/transport/`: AWS, HTTP, shell, external tool wrappers
- `pkg/`: Public API types that external callers can import

---

## 2. CLI Patterns

### Thin CLI, Thick Services
```go
// Good: CLI is just glue
func Run(args []string) int {
    req, err := parseFlags(args)
    if err != nil {
        fmt.Fprintf(os.Stderr, "usage error: %v\n", err)
        return 1
    }

    result, err := service.Execute(ctx, req)
    if err != nil {
        fmt.Fprintf(os.Stderr, "error: %v\n", err)
        return 1
    }

    fmt.Println(result)
    return 0
}

// Bad: Business logic in CLI
func Run(args []string) int {
    // 50 lines of validation, loops, conditionals...
    // Direct exec.Command calls...
    // File I/O and parsing...
}
```

### Flag Parsing
```go
// Prefer ContinueOnError for testability
fs := flag.NewFlagSet("mycommand", flag.ContinueOnError)
fs.StringVar(&cfg.Name, "name", "", "resource name")

if err := fs.Parse(args); err != nil {
    return 1  // Error already printed by flag package
}
```

### Exit Codes
- `0`: Success
- `1`: General error (validation, runtime failure)
- `2`: Usage error (bad flags, missing args)

---

## 3. Context Usage

### Always Pass Context
```go
// Good: Context flows from entry point
func (s *Service) Execute(ctx context.Context, req Request) (*Result, error) {
    return s.client.Do(ctx, req)
}

// Bad: Creating context in service
func (s *Service) Execute(req Request) (*Result, error) {
    ctx := context.Background()  // Lost ability to timeout/cancel
    return s.client.Do(ctx, req)
}
```

### Timeouts for External Calls
```go
ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
defer cancel()

result, err := externalService.Call(ctx, req)
```

### Context Rule of Thumb
Every external call (AWS, HTTP, shell, database) should have a context that can timeout or be cancelled.

---

## 4. Error Handling

### Wrap with Context
```go
result, err := s.doThing(ctx, req)
if err != nil {
    return nil, fmt.Errorf("doThing for %s: %w", req.Name, err)
}
```

### Multi-line for Clarity
```go
// Good: Easy to read and extend
res, err := service.Apply(ctx, req)
if err != nil {
    fmt.Fprintf(os.Stderr, "apply failed: %v\n", err)
    return 1
}

// Bad: Compact but hard to modify
if err := service.Apply(ctx, req); err != nil { fmt.Fprintf(os.Stderr, "apply failed: %v\n", err); return 1 }
```

### Never Ignore Errors
```go
// Bad
json.Marshal(data)      // Error ignored
os.MkdirAll(path, 0755) // Error ignored
f.Write(content)        // Error ignored

// Good
bytes, err := json.Marshal(data)
if err != nil {
    return fmt.Errorf("marshal: %w", err)
}
```

---

## 5. Testing

### Table-Driven Tests
```go
func TestValidate(t *testing.T) {
    tests := []struct {
        name    string
        input   Request
        wantErr bool
    }{
        {"valid", Request{Name: "foo"}, false},
        {"empty name", Request{Name: ""}, true},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            err := Validate(tt.input)
            if (err != nil) != tt.wantErr {
                t.Errorf("got err=%v, wantErr=%v", err, tt.wantErr)
            }
        })
    }
}
```

### Stubbing External Calls
```go
// Service with injectable dependency
type Service struct {
    executor CommandExecutor
}

// Interface for stubbing
type CommandExecutor interface {
    Run(ctx context.Context, cmd string) (string, error)
}

// Test stub
type stubExecutor struct {
    output string
    err    error
}

func (s *stubExecutor) Run(ctx context.Context, cmd string) (string, error) {
    return s.output, s.err
}
```

### Test Helpers
```go
// Isolate environment changes
func withEnv(t *testing.T, key, val string, fn func()) {
    t.Helper()
    old := os.Getenv(key)
    os.Setenv(key, val)
    defer os.Setenv(key, old)
    fn()
}
```

---

## 6. Shell Execution Safety

### Use Existing Helpers
```go
// Good: Use transport helpers
result, err := transport.RunCmdString(ctx, cmd, asRoot)

// Bad: Ad-hoc exec.Command in CLI
cmd := exec.Command("bash", "-c", userInput)  // Injection risk
```

### Avoid String Concatenation
```go
// Bad: Injection vulnerability
cmd := fmt.Sprintf("ls %s", userPath)

// Good: Use structured arguments or encoding
cmd := transport.BuildSafeCommand(userPath)
```

---

## 7. Style

### Follow Go Idioms
- Run `gofmt` on all code
- Use `go vet` and linters
- Follow [Effective Go](https://go.dev/doc/effective_go)

### Naming
- Short, clear names for local variables
- Descriptive names for exported functions
- Avoid stuttering: `user.User` → `user.Record`

### Keep Functions Short
- Aim for functions that fit on one screen
- Extract helpers for complex conditionals
- Single responsibility per function
