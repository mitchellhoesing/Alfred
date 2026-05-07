# SYSTEM ARCHITECTURE & STANDARDS

## 1. Modular Design (OOP & SOLID)
Follow strict Object-Oriented and SOLID principles. Code must be decoupled, maintainable, and type-safe.

* **Single Responsibility (SRP):** Each class and function must have one, and only one, reason to change. Decompose monolithic logic into specialized modules.
* **Open/Closed (OCP):** Software entities should be open for extension but closed for modification. Favor composition over inheritance.
* **Liskov Substitution (LSP):** Subtypes must be entirely substitutable for their base types without breaking functionality.
* **Interface Segregation (ISP):** Prefer many small, specific interfaces over a single general-purpose interface.
* **Dependency Inversion (DIP):** High-level logic must depend on abstractions, not concrete implementations. Use Dependency Injection to provide external services.

### Implementation Constraints:
* **Type Safety:** All function signatures must use explicit Python type hints.
* **Immutability:** Use `@dataclass(frozen=True)` for data structures to prevent side effects.
* **State Management:** Avoid global variables. Encapsulate state within appropriate class scopes.

## 2. Testing Protocol (TDD with unittest)
Adopt a "Test-First" workflow. Functional code is incomplete without verified test coverage.

* **Framework:** Use `unittest`. Tests must inherit from `unittest.TestCase`.
* **Workflow:** 1. Write a failing test in the `tests/` directory. 
    2. Implement the minimum code required to satisfy the test. 
    3. Refactor while maintaining green tests.
* **Isolation:** Mock all external I/O, network requests, and API calls using `unittest.mock`. Tests must be deterministic and run offline.
* **Organization:** Mirror the source directory structure within `tests/`. Use the `test_<module>.py` naming convention.

## 3. Security & Integrity
Security is a primary constraint, not an afterthought.

* **Secrets:** Never hardcode credentials. Use environment variables and `.env` files. Ensure `.env` is in `.gitignore`.
* **Input Sanitization:** Treat all external data (User input, API responses, File reads) as untrusted. Validate types and bounds before processing.
* **Safe Serialization:** Avoid `pickle`. Use `json` or `yaml.safe_load` for data persistence.
* **Least Privilege:** Ensure components only have access to the data and permissions required for their specific task.
* **Error Handling:** Use explicit exception handling. Log detailed errors internally, but provide generic, safe messages to end-users to avoid info-leaks.