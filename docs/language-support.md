# Language capabilities

All nine adapters parse real source with official Tree-sitter grammars. `/api/languages` exposes adapter capabilities. Parsing support must not be confused with complete semantic analysis.

| Language | Main extraction | Established relationships / limits |
| --- | --- | --- |
| Python | AST modules/classes/functions/methods, parameters and Tree-sitter diagnostics | Existing conservative imports, calls, inheritance, decorators and aliases; no runtime dispatch or whole-program typing |
| Java | Tree-sitter declarations and declared receiver/import resolution | Conservative calls/imports/inheritance; overload ambiguity stays unresolved; no compiler type checking |
| JavaScript | Functions, classes, methods and named arrow functions | Selected literal named relative imports and unambiguous top-level calls; default/namespace/CommonJS imports and dynamic receivers incomplete |
| TypeScript | JS-like definitions plus interfaces/enums and selected annotations | Selected named relative imports; no type checker, path mapping or complete overload resolution; TSX grammar used for `.tsx` |
| C | Definitions/prototypes, structs/enums | Literal quoted header imports and unambiguous static calls; macros/linking/preprocessor configurations unresolved |
| C++ | Definitions/prototypes, classes/structs/namespaces | Literal headers and selected qualified/static calls; templates, macros and overloads incomplete |
| Go | Functions, methods, structs/interfaces | Unambiguous same-directory/package top-level calls; module imports and receiver inference incomplete |
| Rust | Functions, structs/enums/traits and impl scopes | Literal modules and selected `use crate::...` aliases; traits, macros, lifetimes and dispatch incomplete |
| C# | Namespaces, types, methods, constructors and properties | Selected explicit class-qualified static calls in the same parsed namespace; instance types, overloads and project references incomplete |

Containment, parameters, selected variable declarations, syntactic exception/base/return references, test references and literal manifest dependencies enrich the common graph where established. A `declared` type/exception/dependency reference is source text, not proof that its implementation is indexed. Not every grammar produces every entity/edge kind. Python/Java analysis is more developed than the seven new adapters.

`.h` uses C by default; C++ headers should use `.hpp`, `.hh` or `.hxx`. `.pyi`, Kotlin, SQL, HTML, CSS and other accepted text remain searchable documents. Inline Rust tests and framework-specific test coverage are incomplete. Configuration links rely on selected explicit literals; framework runtime wiring is not guessed.

Parser recovery errors are static candidates and can reflect unsupported dialects. Unresolved calls/imports stay inspectable without being automatically labelled defects. Calls in comments do not create imports; local/parameter shadowing prevents selected false edges. Cross-language linking and compiler-level dispatch are not implemented.
