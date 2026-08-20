"""Built-in OWASP / CWE security policy corpus used as the RAG knowledge base."""

BUILTIN_POLICIES = [
    {
        "title": "A03:2021 Injection - Parameterized Queries Only",
        "category": "OWASP",
        "cwe": ["CWE-89", "CWE-564"],
        "content": (
            "Never build SQL by concatenating or formatting untrusted input. Use parameterized "
            "queries / prepared statements or an ORM binding layer. In Python that means "
            "cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,)) rather than f-strings. "
            "Reject dynamic table or column names unless they are validated against an allow-list. "
            "Remediation: bind every variable; escape identifiers with the driver's quoting API."
        ),
    },
    {
        "title": "A03:2021 Injection - OS Command Execution",
        "category": "OWASP",
        "cwe": ["CWE-78", "CWE-77"],
        "content": (
            "Do not invoke a shell with user-controlled strings. subprocess must be called with "
            "shell=False and an argument list; os.system and os.popen are forbidden. In Node.js "
            "prefer child_process.execFile or spawn over exec/execSync. Where a shell is truly "
            "required, validate arguments against a strict allow-list and quote with shlex.quote."
        ),
    },
    {
        "title": "Dynamic Code Evaluation Ban",
        "category": "INTERNAL",
        "cwe": ["CWE-95", "CWE-94"],
        "content": (
            "eval, exec, compile, new Function and setTimeout('string') are prohibited in "
            "production code paths. They turn any injection into remote code execution. "
            "Replace with explicit parsers: json.loads for data, ast.literal_eval for literals, "
            "and dispatch dictionaries for dynamic behaviour."
        ),
    },
    {
        "title": "A02:2021 Cryptographic Failures - Hashing and Randomness",
        "category": "OWASP",
        "cwe": ["CWE-327", "CWE-328", "CWE-338"],
        "content": (
            "MD5 and SHA1 are broken and must not be used for signatures, tokens or password "
            "storage. Use SHA-256+ for integrity and bcrypt/argon2/scrypt for passwords. "
            "Random values used for tokens, nonces, salts or session identifiers must come from "
            "secrets (Python) or crypto.randomBytes (Node), never random or Math.random."
        ),
    },
    {
        "title": "A02:2021 Cryptographic Failures - TLS Verification",
        "category": "OWASP",
        "cwe": ["CWE-295"],
        "content": (
            "TLS certificate verification must never be disabled. requests(..., verify=False), "
            "ssl._create_unverified_context and rejectUnauthorized: false enable trivial "
            "machine-in-the-middle attacks. Pin a CA bundle instead of disabling validation."
        ),
    },
    {
        "title": "A07:2021 Identification and Authentication Failures",
        "category": "OWASP",
        "cwe": ["CWE-287", "CWE-798"],
        "content": (
            "Credentials, API keys, JWT signing secrets and database passwords must be loaded "
            "from environment variables or a secret manager, never committed to source. "
            "Hardcoded fallbacks such as os.getenv('SECRET', 'dev-secret') are a finding. "
            "Compare secrets with constant-time functions (hmac.compare_digest)."
        ),
    },
    {
        "title": "A08:2021 Insecure Deserialization",
        "category": "OWASP",
        "cwe": ["CWE-502"],
        "content": (
            "pickle.load, marshal, jsonpickle and yaml.load without SafeLoader execute arbitrary "
            "code contained in the payload. Use json for interchange, yaml.safe_load for config, "
            "and sign any serialized blob that must cross a trust boundary."
        ),
    },
    {
        "title": "A03:2021 Cross-Site Scripting (XSS)",
        "category": "OWASP",
        "cwe": ["CWE-79"],
        "content": (
            "Never write untrusted data into innerHTML, outerHTML, document.write or React's "
            "dangerouslySetInnerHTML. Use textContent, framework escaping, or sanitize with "
            "DOMPurify. Set a strict Content-Security-Policy that forbids inline scripts."
        ),
    },
    {
        "title": "A01:2021 Broken Access Control",
        "category": "OWASP",
        "cwe": ["CWE-284", "CWE-639"],
        "content": (
            "Every endpoint that reads or mutates a resource must verify that the authenticated "
            "principal owns or is authorized for that resource. Do not rely on unguessable IDs. "
            "Deny by default, and centralise authorization checks in middleware or a dependency "
            "rather than duplicating them per handler."
        ),
    },
    {
        "title": "A05:2021 Security Misconfiguration",
        "category": "OWASP",
        "cwe": ["CWE-16", "CWE-489"],
        "content": (
            "Debug modes, stack traces, permissive CORS (allow_origins=['*'] with credentials), "
            "default admin accounts and directory listings must never reach production. "
            "Bind services to explicit interfaces; 0.0.0.0 is only acceptable behind an ingress."
        ),
    },
    {
        "title": "A10:2021 Server-Side Request Forgery (SSRF)",
        "category": "OWASP",
        "cwe": ["CWE-918"],
        "content": (
            "Outbound requests built from user input must validate the destination against an "
            "allow-list of hosts and schemes, resolve DNS once, and block link-local, loopback "
            "and RFC1918 ranges (169.254.169.254 metadata endpoints in particular)."
        ),
    },
    {
        "title": "Resource Leaks and Unbounded Growth",
        "category": "INTERNAL",
        "cwe": ["CWE-401", "CWE-772", "CWE-400"],
        "content": (
            "File handles, sockets, database cursors and subprocesses must be released with a "
            "context manager or try/finally. In JavaScript, every addEventListener, setInterval "
            "and subscription needs a matching teardown in the cleanup path, otherwise detached "
            "DOM nodes and timers accumulate. Caches and in-memory maps keyed by user input must "
            "be bounded (LRU or TTL) to prevent memory exhaustion."
        ),
    },
    {
        "title": "Error Handling and Logic Correctness",
        "category": "INTERNAL",
        "cwe": ["CWE-390", "CWE-396", "CWE-480"],
        "content": (
            "Bare except: and empty catch {} blocks hide defects and turn security failures into "
            "silent success. Catch the narrowest exception type, log with context, and re-raise "
            "when recovery is impossible. Off-by-one boundaries, loose equality (== vs ===), and "
            "unreachable code after return are logic flaws that must be flagged."
        ),
    },
    {
        "title": "A09:2021 Security Logging and Monitoring Failures",
        "category": "OWASP",
        "cwe": ["CWE-778", "CWE-532"],
        "content": (
            "Authentication decisions, authorization failures and administrative actions must be "
            "logged with a correlation id. Conversely, never log secrets, tokens, full payment "
            "data or raw request bodies containing credentials - redact before writing."
        ),
    },
    {
        "title": "Path Traversal and Unsafe File Handling",
        "category": "INTERNAL",
        "cwe": ["CWE-22", "CWE-73"],
        "content": (
            "User-supplied filenames must be normalised with os.path.basename and resolved with "
            "os.path.realpath, then verified to stay inside the intended base directory. "
            "Reject '..' segments, absolute paths and symlinks. Never pass a raw upload name to "
            "open(), send_file() or a static route."
        ),
    },
]
