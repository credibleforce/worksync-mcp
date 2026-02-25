# TypeScript Coding Guidance

TypeScript-specific patterns for maintainable frontend and Node.js codebases.

---

## 1. Type Safety

### Strict Mode
```json
// tsconfig.json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true
  }
}
```

### Avoid `any`
```typescript
// Bad
function process(data: any) { ... }

// Good
function process(data: UserInput) { ... }

// When truly dynamic, use unknown + narrowing
function process(data: unknown) {
  if (isUserInput(data)) {
    // data is now UserInput
  }
}
```

### Define Explicit Types
```typescript
// Good: Clear contract
interface CreateUserRequest {
  name: string;
  email: string;
  role?: 'admin' | 'user';
}

function createUser(req: CreateUserRequest): Promise<User> { ... }
```

---

## 2. Project Structure

### Feature-Based Organization
```
src/
  features/
    users/
      components/
      hooks/
      api.ts
      types.ts
    dashboard/
      ...
  shared/
    components/
    hooks/
    utils/
  lib/
    api-client.ts
    validation.ts
```

### Barrel Exports (Use Sparingly)
```typescript
// features/users/index.ts
export { UserList } from './components/UserList';
export { useUsers } from './hooks/useUsers';
export type { User, CreateUserRequest } from './types';
```

---

## 3. React Patterns

### Component Structure
```typescript
// Props interface at top
interface UserCardProps {
  user: User;
  onSelect?: (user: User) => void;
}

// Component with explicit return type
export function UserCard({ user, onSelect }: UserCardProps): JSX.Element {
  // Hooks first
  const [isExpanded, setIsExpanded] = useState(false);

  // Handlers
  const handleClick = () => {
    onSelect?.(user);
  };

  // Render
  return (
    <div onClick={handleClick}>
      {user.name}
    </div>
  );
}
```

### Custom Hooks
```typescript
// Encapsulate stateful logic
function useUsers() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    fetchUsers()
      .then(setUsers)
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  return { users, loading, error };
}
```

### Avoid Prop Drilling
```typescript
// Use context for deeply nested state
const UserContext = createContext<UserContextValue | null>(null);

export function useUserContext() {
  const ctx = useContext(UserContext);
  if (!ctx) throw new Error('useUserContext must be within UserProvider');
  return ctx;
}
```

---

## 4. Error Handling

### Async/Await with Try-Catch
```typescript
async function fetchUser(id: string): Promise<User> {
  try {
    const response = await api.get(`/users/${id}`);
    return response.data;
  } catch (error) {
    if (error instanceof ApiError) {
      throw new UserNotFoundError(id);
    }
    throw error;
  }
}
```

### Result Types for Expected Failures
```typescript
type Result<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E };

async function parseConfig(path: string): Promise<Result<Config, ParseError>> {
  try {
    const content = await fs.readFile(path, 'utf-8');
    return { ok: true, value: JSON.parse(content) };
  } catch (e) {
    return { ok: false, error: new ParseError(path, e) };
  }
}
```

### Never Swallow Errors
```typescript
// Bad
try {
  await riskyOperation();
} catch {
  // Silent failure
}

// Good
try {
  await riskyOperation();
} catch (error) {
  console.error('Operation failed:', error);
  throw error; // or handle appropriately
}
```

---

## 5. Testing

### Component Tests
```typescript
import { render, screen, fireEvent } from '@testing-library/react';

describe('UserCard', () => {
  it('displays user name', () => {
    render(<UserCard user={{ id: '1', name: 'Alice' }} />);
    expect(screen.getByText('Alice')).toBeInTheDocument();
  });

  it('calls onSelect when clicked', () => {
    const onSelect = jest.fn();
    render(<UserCard user={{ id: '1', name: 'Alice' }} onSelect={onSelect} />);

    fireEvent.click(screen.getByText('Alice'));

    expect(onSelect).toHaveBeenCalledWith({ id: '1', name: 'Alice' });
  });
});
```

### Mock External Dependencies
```typescript
// Mock API client
jest.mock('../lib/api-client', () => ({
  get: jest.fn(),
  post: jest.fn(),
}));

beforeEach(() => {
  jest.clearAllMocks();
});
```

### Test Utilities
```typescript
// Wrapper with providers
function renderWithProviders(ui: React.ReactElement) {
  return render(
    <QueryClientProvider client={queryClient}>
      <UserProvider>
        {ui}
      </UserProvider>
    </QueryClientProvider>
  );
}
```

---

## 6. API Integration

### Type-Safe API Client
```typescript
interface ApiClient {
  get<T>(path: string): Promise<T>;
  post<T, B>(path: string, body: B): Promise<T>;
}

// Usage
const user = await api.get<User>('/users/1');
const created = await api.post<User, CreateUserRequest>('/users', { name: 'Bob' });
```

### Zod for Runtime Validation
```typescript
import { z } from 'zod';

const UserSchema = z.object({
  id: z.string(),
  name: z.string(),
  email: z.string().email(),
});

type User = z.infer<typeof UserSchema>;

// Validate API response
const user = UserSchema.parse(response.data);
```

---

## 7. Style

### Formatting
- Use Prettier with consistent config
- ESLint for code quality
- Husky + lint-staged for pre-commit hooks

### Naming Conventions
- `PascalCase`: Components, Types, Interfaces
- `camelCase`: Functions, variables, hooks
- `SCREAMING_SNAKE_CASE`: Constants
- `kebab-case`: File names (optional, be consistent)

### Import Order
```typescript
// 1. External packages
import React from 'react';
import { useQuery } from '@tanstack/react-query';

// 2. Internal absolute imports
import { api } from '@/lib/api-client';
import { Button } from '@/shared/components';

// 3. Relative imports
import { UserCard } from './UserCard';
import type { UserListProps } from './types';
```
